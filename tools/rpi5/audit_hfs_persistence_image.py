#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Audit a local captured HFS partition through read-only Mac attachments.

Default is a local plan only. --execute attaches ONLY the validated regular
image, never Pi media. This is one component of the persistence proof: it does
not establish capture provenance, a physical write, a reboot or protected SD
bytes. A caller must independently bind those before claiming Gate 4 exit.
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
import subprocess

try:
    from .capture_hfs_reference import validate_fixture
    from .hfs_read_results import FILE_PATHS, validate_entry
    from .hfs_write_results import expected_entries, verify_files
    from .prepare_hfs_fixture import (IMAGE_BYTES, VOLUME, attachment_device,
                                      digest, inspect_image, own_attachment)
except ImportError:
    from capture_hfs_reference import validate_fixture
    from hfs_read_results import FILE_PATHS, validate_entry
    from hfs_write_results import expected_entries, verify_files
    from prepare_hfs_fixture import (IMAGE_BYTES, VOLUME, attachment_device,
                                     digest, inspect_image, own_attachment)

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ('Local image no-repair fsck and independent read-only full file checks; '
         'not physical SD identity, capture provenance, reboot or Gate 4 durability proof')


def owned_path(path):
    path = Path(path).absolute()
    if not path.resolve().is_relative_to((ROOT / 'build/rpi5').resolve()):
        raise ValueError('Use a separate local build/rpi5 artifact, never a device')
    if path.is_symlink():
        raise ValueError('Symlink artifact is not accepted')
    return path


def plan(image, expected_sha256, fixture_path):
    image, fixture_path = owned_path(image), owned_path(fixture_path)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected the independently captured complete partition SHA256')
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    validate_fixture(fixture)
    header = inspect_image(image)
    if digest(image) != expected_sha256:
        raise ValueError('Complete local image differs from the capture hash')
    return dict(image=str(image), image_bytes=IMAGE_BYTES, image_sha256=expected_sha256,
                volume_header=header, fixture=str(fixture_path),
                fixture_reference_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
                fixture_files=fixture['files'], write_files=expected_entries(),
                scope=SCOPE, durability_verified=False)


def same_metadata(before, after):
    return all(getattr(before, key) == getattr(after, key) for key in
               ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink'))


def verify_fixture_files(root, entries):
    """No-follow every component; verify original fixture bytes twice."""
    if len(entries) != len(FILE_PATHS) or {entry['path'] for entry in entries} != FILE_PATHS:
        raise ValueError('Incomplete or repeated original fixture coverage')
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_before = os.fstat(root_fd)
        records = []
        for entry in entries:
            validate_entry(entry)
            if entry.get('mode') != (0o555 if entry['path'] == '/bin/echo' else 0o444):
                raise ValueError('Original fixture permissions changed')
            parent, leaf = entry['path'].lstrip('/').split('/')
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                directory_before = os.fstat(directory)
                fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    before = os.fstat(fd)
                    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                            before.st_dev != root_before.st_dev or directory_before.st_dev != root_before.st_dev or
                            before.st_size != entry['bytes'] or stat.S_IMODE(before.st_mode) != entry['mode']):
                        raise ValueError('Original fixture file type/length/mode changed: ' + entry['path'])
                    for _ in range(2):
                        os.lseek(fd, 0, os.SEEK_SET)
                        data = os.read(fd, entry['bytes'] + 1)
                        if (len(data) != entry['bytes'] or os.read(fd, 1) or
                                hashlib.sha256(data).hexdigest() != entry['sha256'] or
                                not same_metadata(before, os.fstat(fd))):
                            raise ValueError('Original fixture full bytes changed: ' + entry['path'])
                finally:
                    os.close(fd)
                if not same_metadata(directory_before, os.fstat(directory)):
                    raise ValueError('Original fixture directory changed during readback')
            finally:
                os.close(directory)
            records.append(dict(entry))
        if not same_metadata(root_before, os.fstat(root_fd)):
            raise ValueError('Mount root changed during fixture readback')
        return records
    finally:
        os.close(root_fd)


def image_rows(info, image):
    return [row for row in info.get('images', [])
            if Path(row.get('image-path', '')).resolve() == image.resolve()]


def verify_volume(info, mountpoint, device):
    if (info.get('FilesystemType') != 'hfs' or info.get('VolumeName') != VOLUME or
            info.get('MountPoint') != str(mountpoint) or info.get('DeviceNode') != device or
            not os.statvfs(mountpoint).f_flag & os.ST_RDONLY):
        raise ValueError('Expected exact attached HFS volume and independently read-only mount')


def execute(plan_record, output):
    """One fsck attachment, one RO remount, no repairs/retry/physical access."""
    image = Path(plan_record['image'])
    mountpoint = output / 'readonly-mount'
    mountpoint.mkdir()
    state = dict(status='running', started_at=datetime.now(timezone.utc).isoformat(),
                 plan=plan_record, commands=[], detach_count=0, fixture_files=[], write_files=[],
                 durability_verified=False, scope=SCOPE)
    source_paths = {Path(__file__).resolve(), Path(own_attachment.__code__.co_filename).resolve(),
                    Path(verify_files.__code__.co_filename).resolve(), Path(validate_entry.__code__.co_filename).resolve()}
    state['source_inputs_sha256'] = {str(path): digest(path) for path in sorted(source_paths)}
    state_path = output / 'result.json'

    def save():
        state_path.write_text(json.dumps(state, indent=2) + '\n')

    def command(*argv, plist=False):
        record = dict(argv=list(argv), status='started')
        state['commands'].append(record)
        number = len(state['commands'])
        save()
        try:
            result = subprocess.run(argv, capture_output=True, timeout=180)
        except BaseException as error:
            record.update(status='unknown', error=str(error)); save()
            raise
        stdout, stderr = output / f'command-{number}.stdout', output / f'command-{number}.stderr'
        stdout.write_bytes(result.stdout); stderr.write_bytes(result.stderr)
        record.update(status='complete', returncode=result.returncode,
                      stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
        save()
        if result.returncode != 0:
            raise RuntimeError('Read-only audit command failed: ' + repr(argv))
        return plistlib.loads(result.stdout) if plist else result.stdout

    @contextmanager
    def attached(mounted):
        # Refuse pre-existing attachment: we do not own it, even if read-only.
        info = command('hdiutil', 'info', '-plist', plist=True)
        if image_rows(info, image):
            raise ValueError('Image already attached; do not disturb an existing attachment')
        attempted = False
        try:
            attempted = True
            command('hdiutil', 'attach', str(image), '-readonly', '-nobrowse', '-noautoopen',
                    '-noautofsck', *(['-mountpoint', str(mountpoint)] if mounted else ['-nomount']),
                    '-plist', plist=True)
            info = command('hdiutil', 'info', '-plist', plist=True)
            device = own_attachment(info, image, mountpoint if mounted else None)
            yield device
        finally:
            if attempted:
                # Also covers attach timeout/validation failure; resolve ownership
                # afresh. Ambiguity/info failure never detaches an inferred device.
                info = command('hdiutil', 'info', '-plist', plist=True)
                if image_rows(info, image):
                    device = attachment_device(info, image)
                    command('hdiutil', 'detach', device)
                    state['detach_count'] += 1; save()

    save()
    try:
        current = plan(image, plan_record['image_sha256'], Path(plan_record['fixture']))
        if current != plan_record:
            raise ValueError('Input bytes/header/reference changed after plan')
        before = image.lstat()
        with attached(False) as device:
            # -n forbids repairs; verified attachment is read-only independently.
            command('/sbin/fsck_hfs', '-fn', device)
        with attached(True) as device:
            info = command('diskutil', 'info', '-plist', str(mountpoint), plist=True)
            verify_volume(info, mountpoint, device)
            (output / 'volume-info.plist').write_bytes(plistlib.dumps(info))
            state['fixture_files'] = verify_fixture_files(mountpoint, plan_record['fixture_files'])
            state['write_files'] = verify_files(mountpoint)
            if verify_files(mountpoint) != state['write_files']:
                raise ValueError('Unstable second complete write-vector read')
            verify_volume(command('diskutil', 'info', '-plist', str(mountpoint), plist=True), mountpoint, device)
            own_attachment(command('hdiutil', 'info', '-plist', plist=True), image, mountpoint)
        if (state['detach_count'] != 2 or image_rows(command('hdiutil', 'info', '-plist', plist=True), image) or
                not same_metadata(before, image.lstat()) or
                plan(image, plan_record['image_sha256'], Path(plan_record['fixture'])) != plan_record or
                any(digest(Path(path)) != sha for path, sha in state['source_inputs_sha256'].items())):
            raise ValueError('Image or ownership changed during read-only audit')
        state.update(status='local_image_audit_passed', readonly_fsck_verified=True,
                     readonly_remount_verified=True, image_unchanged=True,
                     mac_attachment_detached=True)
    except BaseException as error:
        state.update(status='failed', error=str(error))
        raise
    finally:
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    output = owned_path(args.output)
    if output.exists():
        raise ValueError('Use a fresh audit output; preserve previous outcomes')
    record = plan(args.image, args.expected_sha256, args.fixture)
    output.mkdir()
    (output / 'plan.json').write_text(json.dumps(record, indent=2) + '\n')
    if args.execute:
        execute(record, output)
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
