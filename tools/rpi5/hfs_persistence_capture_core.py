# SPDX-License-Identifier: BSD-2-Clause
"""Fixed SD read-only post-write capture; embedded on verified SSD Linux.

PLAN is supplied by the controller, never inferred from network discovery.
Every SD descriptor is read-only. Only a fresh NVMe artifact receives writes.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import struct
import subprocess

CHUNK = 1024 * 1024
IMAGE_BYTES = 134217728
IMAGE_NAME = 'hfs-partition.after-write.img'


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def identity(plan):
    expected = plan['expected']
    root = ' '.join(command('findmnt', '-no', 'SOURCE,FSTYPE,UUID', '/').split())
    layout = json.loads(command('sfdisk', '--json', '/dev/mmcblk0'))['partitiontable']
    parts = {}
    for name, node in (('boot_partition', '/dev/mmcblk0p1'), ('hfs_partition', '/dev/mmcblk0p2')):
        fields = dict(line.split('=', 1) for line in command('blkid', '-o', 'export', node).splitlines() if '=' in line)
        parts[name] = {key: fields.get(key) for key in expected[name]}
    base = Path('/sys/block/mmcblk0/device')
    observed = dict(root=root, layout=layout, card={key: (base / key).read_text().strip() for key in ('cid', 'csd')},
                    bytes=int(Path('/sys/block/mmcblk0/size').read_text()) * 512,
                    partition_start=int(Path('/sys/class/block/mmcblk0p2/start').read_text()),
                    partition_sectors=int(Path('/sys/class/block/mmcblk0p2/size').read_text()), **parts)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if (observed != expected or command('hostname') != 'kamidana' or
            boot_id != plan['linux_boot_id_after_write'] or boot_id == plan['linux_boot_id_before_write']):
        raise ValueError('Exact card/layout/SSD root and intervening new boot are required')
    for node in ('/dev/mmcblk0', '/dev/mmcblk0p1', '/dev/mmcblk0p2'):
        mounted = subprocess.run(['findmnt', '-rn', '-S', node], capture_output=True, text=True, timeout=10)
        if mounted.returncode != 1 or mounted.stdout.strip():
            raise ValueError('SD already mounted or lookup failed; no automatic unmount')
        holders = Path('/sys/class/block') / Path(node).name / 'holders'
        if not holders.is_dir() or any(holders.iterdir()):
            raise ValueError('Unexpected SD holder')
    automount = subprocess.run(['systemctl', 'is-active', '--quiet', 'udisks2', 'autofs'], timeout=10)
    if automount.returncode not in (3, 4):
        raise ValueError('Automounter active or lookup failed')
    return dict(identity=observed, boot_id=boot_id, hostname='kamidana')


def full_hash(path, size):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != size
                or before.st_dev != Path('/').stat().st_dev):
            raise ValueError('Preserved NVMe artifact type/size differs')
        value = hashlib.sha256()
        for offset in range(0, size, CHUNK):
            length = min(CHUNK, size - offset); data = os.pread(fd, length, offset)
            if len(data) != length: raise RuntimeError('Short preserved artifact read')
            value.update(data)
        after = os.fstat(fd)
        if any(getattr(before, key) != getattr(after, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            raise ValueError('Preserved NVMe artifact changed during verification')
        return value.hexdigest()
    finally:
        os.close(fd)


def verify_backups(plan):
    for row in plan['nvme_backups']:
        path = Path(row['path'])
        if path.parent.resolve() != path.parent or path.parent.stat().st_dev != Path('/').stat().st_dev:
            raise ValueError('Backup is not on the verified NVMe filesystem')
        if full_hash(path, row['bytes']) != row['sha256']:
            raise ValueError('Preserved NVMe backup differs: ' + str(path))


def snapshot(node, capacity, length):
    allowed = {'/dev/mmcblk0': (128177930240, 512), '/dev/mmcblk0p1': (536870912, 536870912),
               '/dev/mmcblk0p2': (IMAGE_BYTES, IMAGE_BYTES)}
    if node not in allowed or (capacity, length) != allowed[node]:
        raise ValueError('Only the exact disposable SD extents may be read')
    fd = os.open(node, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISBLK(info.st_mode) or info.st_rdev != os.stat(node).st_rdev or
                struct.unpack('=Q', fcntl.ioctl(fd, 0x80081272, bytes(8)))[0] != capacity):
            raise ValueError('SD descriptor identity/capacity differs')
        value = hashlib.sha256()
        for offset in range(0, length, CHUNK):
            wanted = min(CHUNK, length - offset); data = os.pread(fd, wanted, offset)
            if len(data) != wanted: raise RuntimeError('Short SD snapshot read')
            value.update(data)
        return dict(device=node, bytes=length, sha256=value.hexdigest())
    finally:
        os.close(fd)


def copy_hfs(directory):
    """Complete second SD read into a fresh fsynced/readback-verified NVMe file."""
    source = os.open('/dev/mmcblk0p2', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    target = None
    try:
        info = os.fstat(source)
        if (not stat.S_ISBLK(info.st_mode) or info.st_rdev != os.stat('/dev/mmcblk0p2').st_rdev or
                struct.unpack('=Q', fcntl.ioctl(source, 0x80081272, bytes(8)))[0] != IMAGE_BYTES or
                not stat.S_ISDIR(os.fstat(directory).st_mode) or
                os.fstat(directory).st_dev != Path('/').stat().st_dev):
            raise ValueError('Expected identified HFS block descriptor and NVMe directory')
        target = os.open(IMAGE_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        value = hashlib.sha256()
        for offset in range(0, IMAGE_BYTES, CHUNK):
            length = min(CHUNK, IMAGE_BYTES - offset); data = os.pread(source, length, offset)
            if len(data) != length: raise RuntimeError('Short HFS capture read')
            value.update(data); sent = 0
            for _ in range(16):
                try: count = os.pwrite(target, data[sent:], offset + sent)
                except InterruptedError: continue
                if type(count) is not int or not 0 < count <= len(data) - sent:
                    raise RuntimeError('Invalid NVMe capture progress')
                sent += count
                if sent == len(data): break
            if sent != len(data): raise RuntimeError('NVMe capture progress limit')
        os.fsync(target)
        info = os.fstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != IMAGE_BYTES:
            raise ValueError('NVMe capture file identity/length differs')
        checked = hashlib.sha256()
        for offset in range(0, IMAGE_BYTES, CHUNK):
            length = min(CHUNK, IMAGE_BYTES - offset); data = os.pread(target, length, offset)
            if len(data) != length: raise RuntimeError('Short NVMe capture readback')
            checked.update(data)
        if checked.hexdigest() != value.hexdigest(): raise ValueError('NVMe capture readback differs')
        owner = pwd.getpwnam('sandrzej')
        os.fchown(target, owner.pw_uid, owner.pw_gid) # User-readable SCP source, never SD.
        os.fsync(target); os.fsync(directory)
        return dict(device='/dev/mmcblk0p2', bytes=IMAGE_BYTES, sha256=value.hexdigest(), saved_as=IMAGE_NAME)
    finally:
        if target is not None: os.close(target)
        os.close(source)


def run_capture(plan):
    if os.geteuid() != 0: raise ValueError('Root required for read-only SD descriptors')
    before = identity(plan); verify_backups(plan)
    run = Path(plan['run'])
    if (run.resolve() != run or run.stat().st_dev != Path('/').stat().st_dev or any(run.iterdir())):
        raise ValueError('Fresh verified NVMe capture directory required')
    mbr = snapshot('/dev/mmcblk0', 128177930240, 512)
    boot = snapshot('/dev/mmcblk0p1', 536870912, 536870912)
    first = snapshot('/dev/mmcblk0p2', IMAGE_BYTES, IMAGE_BYTES)
    if mbr['sha256'] != plan['mbr_sha256'] or boot['sha256'] != plan['boot_sha256']:
        raise ValueError('Protected complete MBR/FAT differs after write boot')
    if first['sha256'] == plan['fixture_sha256']:
        raise ValueError('HFS image did not change; no persisted write batch')
    directory = os.open(run, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: copied = copy_hfs(directory)
    finally: os.close(directory)
    last = snapshot('/dev/mmcblk0p2', IMAGE_BYTES, IMAGE_BYTES)
    mbr_after = snapshot('/dev/mmcblk0', 128177930240, 512)
    boot_after = snapshot('/dev/mmcblk0p1', 536870912, 536870912)
    after = identity(plan); verify_backups(plan)
    if (before != after or first['sha256'] != copied['sha256'] or first != last or
            mbr != mbr_after or boot != boot_after or
            full_hash(run / IMAGE_NAME, IMAGE_BYTES) != copied['sha256']):
        raise ValueError('Unstable post-write capture or protected SD bytes')
    return dict(status='captured_not_durability', run=str(run), identity=before,
                protected=dict(mbr=mbr, boot=boot), hfs_reads=[first, copied, last],
                nvme_backups_verified=plan['nvme_backups'], sd_write_operations=0, sd_mount_operations=0,
                image=str(run / IMAGE_NAME), image_sha256=copied['sha256'], durability_verified=False,
                scope='New Linux boot + stable complete raw capture/protected bytes; fsck/RO full file audit still required')
