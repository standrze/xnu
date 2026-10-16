# SPDX-License-Identifier: BSD-2-Clause
"""Fixed-device read-only snapshots on verified NVMe; embedded by write installer.

Does not discover targets, mount, write SD, repair, retry or reboot. Caller must
first verify exact Linux/card identity, holders, unmounted media and automounters.
"""
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import struct

CHUNK = 1024 * 1024


def block_snapshot(node, capacity, length, directory=None, name=None):
    allowed = {'/dev/mmcblk0': (128177930240, 512),
               '/dev/mmcblk0p1': (536870912, 536870912),
               '/dev/mmcblk0p2': (134217728, 134217728)}
    if node not in allowed or (capacity, length) != allowed[node]:
        raise ValueError('Only exact disposable SD snapshot extents are allowed')
    names = {'/dev/mmcblk0': 'mbr.before-write.bin',
             '/dev/mmcblk0p1': 'boot-partition.before-write.img',
             '/dev/mmcblk0p2': 'hfs-partition.before.img'}
    if (directory is None) != (name is None) or (name is not None and name != names[node]):
        raise ValueError('Unexpected backup destination')
    source = os.open(node, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    target = None
    try:
        info = os.fstat(source)
        if not stat.S_ISBLK(info.st_mode) or info.st_rdev != os.stat(node).st_rdev:
            raise ValueError('Snapshot source is not the exact block device')
        size = struct.unpack('=Q', fcntl.ioctl(source, 0x80081272, bytes(8)))[0]
        if size != capacity:
            raise ValueError('Snapshot descriptor capacity differs')
        if directory is not None:
            if not stat.S_ISDIR(os.fstat(directory).st_mode):
                raise ValueError('Backup directory descriptor required')
            target = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        digest = hashlib.sha256()
        for offset in range(0, length, CHUNK):
            wanted = min(CHUNK, length-offset)
            data = os.pread(source, wanted, offset)
            if len(data) != wanted:
                raise RuntimeError('Short snapshot source read')
            digest.update(data)
            if target is not None:
                done = 0
                for _ in range(16):
                    try:
                        count = os.pwrite(target, data[done:], offset+done)
                    except InterruptedError:
                        continue
                    if type(count) is not int or not 0 < count <= len(data)-done:
                        raise RuntimeError('Invalid snapshot destination progress')
                    done += count
                    if done == len(data):
                        break
                if done != len(data):
                    raise RuntimeError('Snapshot write progress limit')
        value = digest.hexdigest()
        if target is not None:
            os.fsync(target)
            observed = os.fstat(target)
            if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1 or observed.st_size != length:
                raise RuntimeError('Snapshot destination identity/length differs')
            checked = hashlib.sha256()
            for offset in range(0, length, CHUNK):
                data = os.pread(target, min(CHUNK, length-offset), offset)
                if len(data) != min(CHUNK, length-offset):
                    raise RuntimeError('Short snapshot readback')
                checked.update(data)
            if checked.hexdigest() != value:
                raise RuntimeError('Snapshot readback differs')
            os.fsync(directory)
        return dict(device=node, bytes=length, sha256=value, saved_as=name)
    finally:
        if target is not None:
            os.close(target)
        os.close(source)


def check_boot_id(plan):
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['linux_boot_id']:
        raise ValueError('Linux boot changed; fresh identity required')


def prepare_write_backups(plan):
    check_boot_id(plan)
    directory = os.open(plan['run'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        records = [block_snapshot('/dev/mmcblk0', 128177930240, 512, directory, 'mbr.before-write.bin'),
                   block_snapshot('/dev/mmcblk0p1', 536870912, 536870912, directory, 'boot-partition.before-write.img'),
                   block_snapshot('/dev/mmcblk0p2', 134217728, 134217728, directory, 'hfs-partition.before.img')]
        if records[0]['sha256'] != plan['current_mbr_sha256'] or records[2]['sha256'] != plan['fixture_sha256']:
            raise ValueError('Current MBR/HFS differs from accepted fixture installation')
        if (plan.get('profile') in ('write-diagnostic','write-cache-diagnostic')
                and records[1]['sha256']!=plan['expected_boot_before_sha256']):
            raise ValueError('Complete installed write-trial FAT baseline changed')
        return records
    finally:
        os.close(directory)


def finish_write_install(plan, records):
    check_boot_id(plan)
    mbr = block_snapshot('/dev/mmcblk0', 128177930240, 512)
    boot = block_snapshot('/dev/mmcblk0p1', 536870912, 536870912)
    hfs = block_snapshot('/dev/mmcblk0p2', 134217728, 134217728)
    if mbr['sha256'] != plan['current_mbr_sha256'] or hfs['sha256'] != plan['fixture_sha256']:
        raise ValueError('MBR/HFS changed during image installation')
    return dict(before=records, after=dict(mbr=mbr, boot=boot, hfs=hfs),
                linux_boot_id=plan['linux_boot_id'], sd_data_writes=0, hfs_mounts=0,
                scope='NVMe backup/readback and post-install raw boot baseline; not XNU writes or durability')
