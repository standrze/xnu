#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Create/verify a new local HFS+ data image. Never touches Pi or physical media.

All formatter inputs name a fresh image/source directory, never a device node.
Only an attachment proven to belong to that exact image may be detached.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import subprocess
import tempfile

try:
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    from prepare_pid1 import inspect as inspect_macho

ROOT = Path(__file__).resolve().parents[2]
IMAGE_BYTES = 128 * 1024 * 1024
VOLUME = 'XNU_G4_READ'
PROOF = b'RPI5XNU:GATE4:HFS_READ_PROOF:v1\n'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect_header(data, size):
    if len(data) != 512 or size != IMAGE_BYTES:
        raise ValueError('Unexpected fixture/volume-header size')
    signature, version, attributes = struct.unpack_from('>HHI', data)
    block_size, total_blocks, free_blocks = struct.unpack_from('>III', data, 40)
    if (signature != 0x482b or version != 4 or not attributes & 0x100 or
            attributes & (0x2000 | 0x4000 | 0x40000000) or
            block_size < 512 or block_size & (block_size - 1) or
            block_size * total_blocks != size or free_blocks > total_blocks):
        raise ValueError('Not a clean, unjournaled, unprotected, standalone HFS+ fixture')
    return {'signature': 'H+', 'version': version, 'attributes': hex(attributes),
            'block_size': block_size, 'total_blocks': total_blocks, 'free_blocks': free_blocks}


def inspect_image(image):
    info = image.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != IMAGE_BYTES:
        raise ValueError('Image is not the expected standalone raw regular file')
    fd = os.open(image, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd) != info:
            raise ValueError('Image changed during open')
        primary = os.pread(fd, 512, 1024)
        alternate = os.pread(fd, 512, IMAGE_BYTES - 1024)
        header = inspect_header(primary, IMAGE_BYTES)
        alternate_header = inspect_header(alternate, IMAGE_BYTES)
        # Apple updates the alternate only for selected critical changes
        # (hfs_flushvolumeheader/altflush), not every free-space counter change.
        # Require matching geometry/clean state, not identical mutable counters.
        if any(alternate_header[key] != value for key, value in header.items() if key != 'free_blocks'):
            raise ValueError('Primary and alternate volume-header geometry/state disagree')
    finally:
        os.close(fd)
    return {**header, 'alternate_free_blocks': alternate_header['free_blocks']}


def attachment_record(info, image):
    matches = [row for row in info.get('images', [])
               if Path(row.get('image-path', '')).resolve() == image.resolve()]
    if len(matches) != 1:
        raise ValueError('Fresh image lacks a unique attachment')
    return matches[0]


def attachment_device(info, image):
    entities = attachment_record(info, image).get('system-entities', [])
    if len(entities) != 1 or not re.fullmatch(r'/dev/disk[0-9]+', entities[0].get('dev-entry', '')):
        raise ValueError('Unexpected virtual image device layout; refusing detach')
    return entities[0]['dev-entry']


def own_attachment(info, image, mountpoint=None):
    row = attachment_record(info, image)
    if row.get('writeable') is not False:
        raise ValueError('Fresh image attachment is not read-only')
    if (row.get('blocksize') != 512 or row.get('blockcount') != IMAGE_BYTES // 512 or
            row.get('image-encrypted') is not False):
        raise ValueError('Virtual image geometry/encryption differs from the raw fixture')
    entities = row.get('system-entities', [])
    mounted = [row for row in entities if row.get('mount-point')]
    # layout NONE must expose one whole virtual HFS device, no partitions.
    if (len(entities) != 1 or
            (bool(mounted) if mountpoint is None else len(mounted) != 1 or mounted[0]['mount-point'] != str(mountpoint)) or
            # Raw layout-NONE media can have no partition content hint. Its
            # filesystem is verified by headers/fsck/diskutil, not that hint.
            entities[0].get('content-hint') not in ('', 'Apple_HFS') or
            not re.fullmatch(r'/dev/disk[0-9]+', entities[0].get('dev-entry', ''))):
        raise ValueError('Unexpected virtual image device/mount layout')
    return entities[0]['dev-entry']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--userland', required=True, type=Path)
    args = parser.parse_args()
    executable = args.userland.resolve()
    if not executable.is_relative_to((ROOT / 'build/rpi5').resolve()) or not executable.is_file():
        parser.error('Use a separately built local Pi userland executable')
    raw = executable.read_bytes()
    executable_report = inspect_macho(raw)
    run = Path(tempfile.mkdtemp(prefix='hfs-read-fixture-', dir=ROOT / 'build/rpi5')).resolve()
    source, mountpoint = run / 'source', run / 'readonly-mount'
    source.mkdir(); mountpoint.mkdir()
    files = {
        'etc/proof.txt': (PROOF, 0o444),
        'etc/empty': (b'', 0o444),
        'etc/cross-page.bin': (bytes(range(256)) * 129 + b'GATE4 END\n', 0o444),
        'etc/recovery.sh': (b'echo HFS_SCRIPT_BEGIN\ncat /mnt/hfs/etc/proof.txt\necho HFS_SCRIPT_END\n', 0o444),
        'bin/echo': (raw, 0o555),
    }
    expected = []
    for name, (data, mode) in files.items():
        path = source / name
        path.parent.mkdir(exist_ok=True)
        with path.open('xb') as output:
            output.write(data)
        path.chmod(mode)
        expected.append({'path': '/' + name, 'bytes': len(data), 'mode': mode,
                         'sha256': hashlib.sha256(data).hexdigest()})
    commands = []

    def command(*argv, plist=False, timeout=180):
        commands.append(list(argv))
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
        (run / f'command-{len(commands)}.stdout').write_bytes(result.stdout)
        (run / f'command-{len(commands)}.stderr').write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f'Command failed: {argv!r}\n{result.stdout.decode(errors="replace")}{result.stderr.decode(errors="replace")}')
        return plistlib.loads(result.stdout) if plist else result.stdout

    image = run / 'hfs-read.cdr'
    command('hdiutil', 'create', '-size', '128m', '-srcfolder', str(source),
            '-fs', 'HFS+', '-volname', VOLUME, '-layout', 'NONE', '-format', 'UDTO',
            '-nospotlight', '-anyowners', str(image))
    header = inspect_image(image)
    before = digest(image)
    detaches = 0

    @contextmanager
    def attached(mount):
        nonlocal detaches
        try:
            command('hdiutil', 'attach', str(image), '-readonly', '-nobrowse', '-noautoopen',
                    '-noautofsck', *(['-mountpoint', str(mountpoint)] if mount else ['-nomount']),
                    '-plist', plist=True)
            info = command('hdiutil', 'info', '-plist', plist=True)
            yield own_attachment(info, image, mountpoint if mount else None)
        finally:
            # Resolve the exact image's ownership again, including after a
            # post-attach validation failure. Never detach an inferred device.
            info = command('hdiutil', 'info', '-plist', plist=True)
            matching = [row for row in info.get('images', [])
                        if Path(row.get('image-path', '')).resolve() == image.resolve()]
            if matching:
                device = attachment_device(info, image)
                command('hdiutil', 'detach', device)
                detaches += 1

    # fsck_hfs requires a device ioctl, not a regular file. Its target is the
    # verified read-only virtual attachment of this fresh image, never Pi media.
    with attached(False) as device:
        command('/sbin/fsck_hfs', '-fn', device)
    with attached(True) as device:
        volume_info = command('diskutil', 'info', '-plist', str(mountpoint), plist=True)
        if (volume_info.get('FilesystemType') != 'hfs' or volume_info.get('VolumeName') != VOLUME or
                volume_info.get('MountPoint') != str(mountpoint) or
                volume_info.get('DeviceNode') != device or not os.statvfs(mountpoint).f_flag & os.ST_RDONLY):
            raise ValueError('Mounted image is not the expected read-only HFS volume')
        for entry in expected:
            path = mountpoint / entry['path'].lstrip('/')
            status = path.lstat()
            if (not stat.S_ISREG(status.st_mode) or status.st_size != entry['bytes'] or
                    stat.S_IMODE(status.st_mode) != entry['mode'] or digest(path) != entry['sha256']):
                raise ValueError('Mounted fixture file differs: ' + entry['path'])
            # Deliberately verify independent complete reads twice.
            if digest(path) != entry['sha256']:
                raise ValueError('Unstable mounted fixture file: ' + entry['path'])
        (run / 'volume-info.plist').write_bytes(plistlib.dumps(volume_info))
    if detaches != 2 or digest(image) != before or inspect_image(image) != header:
        raise ValueError('Read-only mount changed the raw fixture image')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'image': str(image),
              'image_sha256': before, 'image_bytes': IMAGE_BYTES, 'image_sectors': IMAGE_BYTES // 512,
              'volume_name': VOLUME, 'volume_header': header, 'files': expected,
              'userland': str(executable), 'userland_sha256': digest(executable),
              'executable_report': executable_report, 'commands': commands,
              'script_sha256': digest(Path(__file__)), 'mac_readonly_mount_verified': True,
              'mac_attachment_detached': detaches == 2, 'readonly_fsck_verified': True, 'pi_sd_changes': 0,
              'scope': 'Clean local HFS+ raw image and Mac readback only; not Pi SD reads, HFS mounts or durability'}
    (run / 'reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(run)


if __name__ == '__main__':
    main()
