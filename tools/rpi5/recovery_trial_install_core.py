# SPDX-License-Identifier: BSD-2-Clause
"""Fixed FAT file publication with owned mounts; injected unchanged helpers.

Never reboot, modify config/firmware, mount HFS, retry, or roll back implicitly.
Both stage and explicit restore snapshot every protected extent first.
"""
import json
import os
from pathlib import Path
import re
import subprocess

MOUNTPOINT = '/mnt/xnu-probe'
NODE = '/dev/mmcblk0p1'
NAMES = {
    'watchdog-only-trial': ('probe.socket-identity-passed-20261012.bin', 'probe.watchdog-only-20261012.tmp',
                            'socket-identity-passed.bin'),
    'watchdog-only-restore': ('probe.watchdog-only-trial-20261012.bin', 'probe.socket-identity-restored-20261012.tmp',
                              'watchdog-only-trial.bin'),
}
EXTENTS = (
    ('mbr', '/dev/mmcblk0', 128177930240, 512, 'mbr.before-write.bin'),
    ('boot', NODE, 536870912, 536870912, 'boot-partition.before-write.img'),
    ('hfs', '/dev/mmcblk0p2', 134217728, 134217728, 'hfs-partition.before.img'),
)


def command(args):
    return subprocess.run(args, text=True, capture_output=True, timeout=20)


def mount_record(run, mode=None, required=True):
    result = run(['findmnt', '--json', '--mountpoint', MOUNTPOINT, '-o', 'ID,SOURCE,FSTYPE,OPTIONS,TARGET'])
    if result.returncode == 1 and not result.stdout.strip() and not required: return None
    if result.returncode: raise ValueError('Exact mount lookup failed')
    rows = json.loads(result.stdout).get('filesystems')
    if not isinstance(rows, list) or len(rows) != 1: raise ValueError('Ambiguous mount')
    row = rows[0]
    if set(row) != {'id', 'source', 'fstype', 'options', 'target'}: raise ValueError('Unexpected mount fields')
    if isinstance(row['id'], bool) or not isinstance(row['id'], (int, str)): raise ValueError('Invalid mount ID')
    identifier = int(row['id'])
    if identifier <= 0 or not isinstance(row['options'], str): raise ValueError('Invalid mount ID/options')
    options = set(row['options'].split(','))
    access = options & {'ro', 'rw'}
    if (row['source'] != NODE or row['fstype'] != 'vfat' or row['target'] != MOUNTPOINT or
            not {'nosuid', 'nodev', 'noexec'}.issubset(options) or len(access) != 1 or
            (mode is not None and access != {mode})):
        raise ValueError('Not exact guarded FAT mount')
    return dict(id=identifier, source=NODE, fstype='vfat', target=MOUNTPOINT, mode=next(iter(access)))


def invoke(run, args):
    result = run(args)
    if result.returncode: raise ValueError('Mount operation failed: '+repr(args)+' '+result.stderr[:512])


def publish(directory, candidate, plan, helper, guard):
    """Existing immutable copy/hash helpers, distinct fixed names, guarded rename."""
    backup, temporary, _ = NAMES[plan['profile']]
    old_hash, new_hash = plan['old_image_sha256'], plan['new_image_sha256']
    if any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in (old_hash, new_hash)) or old_hash == new_hash:
        raise ValueError('Distinct exact hashes required')
    guard('rw')
    if helper.digest_fd(candidate) != new_hash: raise ValueError('Candidate changed')
    old = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        if helper.digest_fd(old) != old_hash: raise ValueError('Current image changed')
        for name in (backup, temporary):
            try: os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError: continue
            raise ValueError('Partial/existing artifact; never retry: '+name)
        guard('rw'); helper.copy_image(old, directory, backup, old_hash); os.fsync(directory)
        guard('rw'); helper.copy_image(candidate, directory, temporary, new_hash)
        current = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            if helper.digest_fd(current) != old_hash: raise ValueError('Current image changed before publication')
        finally: os.close(current)
        guard('rw')
        os.rename(temporary, 'probe.bin', src_dir_fd=directory, dst_dir_fd=directory); os.fsync(directory)
        guard('rw')
        current = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            if helper.digest_fd(current) != new_hash: raise ValueError('Publication readback differs')
        finally: os.close(current)
    finally: os.close(old)
    return dict(image_sha256=new_hash, preserved_sd_image_sha256=old_hash, sd_backup=backup,
                temporary_published=True, power_loss_atomicity_claimed=False)


def execute(plan, capture, helper, snapshots, reference, run=None):
    if os.geteuid() != 0 or plan['profile'] not in NAMES: raise ValueError('Root and fixed profile required')
    run = run or command
    before = capture.identity(plan['identity_binding']); capture.verify_backups(plan)
    work = Path(plan['run'])
    if (work.resolve() != work or work.stat().st_dev != Path('/').stat().st_dev or
            {p.name for p in work.iterdir()} != {'candidate.bin'}): raise ValueError('Fresh NVMe run required')
    candidate = os.open(work/'candidate.bin', os.O_RDONLY | os.O_NOFOLLOW)
    nvme = os.open(work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory, owned = None, None
    try:
        if helper.digest_fd(candidate) != plan['new_image_sha256']: raise ValueError('Candidate differs')
        records = [snapshots.block_snapshot(node, capacity, length, nvme, name)
                   for _, node, capacity, length, name in EXTENTS]
        if {key:r['sha256'] for (key, *_), r in zip(EXTENTS, records)} != plan['protected_sha256']:
            raise ValueError('Complete MBR/FAT/HFS baseline differs')
        if capture.identity(plan['identity_binding']) != before: raise ValueError('Identity changed during backups')
        mp = Path(MOUNTPOINT)
        if mp.resolve() != mp or not mp.is_dir() or any(mp.iterdir()) or mount_record(run, required=False) is not None:
            raise ValueError('Empty unmounted canonical mountpoint required')
        invoke(run, ['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', NODE, MOUNTPOINT])
        owned = mount_record(run, 'ro')
        directory = os.open(mp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        def guard(mode):
            current = mount_record(run, mode)
            if any(current[k] != owned[k] for k in ('id', 'source', 'fstype', 'target')):
                raise ValueError('Mount ownership changed; no cleanup of foreign mount')
            if (os.fstat(directory).st_dev, os.fstat(directory).st_ino) != (mp.stat().st_dev, mp.stat().st_ino):
                raise ValueError('Mount directory descriptor detached')
            if (capture.command('findmnt', '-no', 'SOURCE,FSTYPE,UUID', '/').split() !=
                    plan['identity_binding']['expected']['root'].split() or
                    Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['linux_boot_id']):
                raise ValueError('SSD root/boot changed')
        expected = dict(plan['protected_files'], **{'probe.bin':plan['old_image_sha256']})
        guard('ro'); files = reference.read_files(directory, expected)
        if not reference.configured_return(files): raise ValueError('Configured SSD return absent')
        old = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        previous = NAMES[plan['profile']][2]
        try: helper.copy_image(old, nvme, previous, plan['old_image_sha256']); os.fsync(nvme)
        finally: os.close(old)
        if capture.full_hash(work/previous, (work/previous).stat().st_size) != plan['old_image_sha256']:
            raise ValueError('NVMe current-image backup differs')
        guard('ro')
        invoke(run, ['mount', '-o', 'remount,rw,nosuid,nodev,noexec', MOUNTPOINT])
        guard('rw'); result = publish(directory, candidate, plan, helper, guard)
        guard('rw'); invoke(run, ['mount', '-o', 'remount,ro,nosuid,nodev,noexec', MOUNTPOINT]); guard('ro')
        expected.update({'probe.bin':plan['new_image_sha256'], result['sd_backup']:plan['old_image_sha256']})
        reference.read_files(directory, expected); guard('ro')
    finally:
        # A live directory FD keeps a Linux mount busy. Close it before the
        # owned-mount lookup/unmount, including every exceptional path.
        if directory is not None: os.close(directory); directory = None
        try:
            if owned is not None:
                current = mount_record(run)
                if any(current[k] != owned[k] for k in ('id', 'source', 'fstype', 'target')):
                    raise ValueError('Mount replaced; manual inspection, no cleanup')
                if current['mode'] == 'rw':
                    invoke(run, ['mount', '-o', 'remount,ro,nosuid,nodev,noexec', MOUNTPOINT])
                    if mount_record(run, 'ro')['id'] != owned['id']: raise ValueError('Mount replaced during cleanup')
                invoke(run, ['umount', MOUNTPOINT])
                if mount_record(run, required=False) is not None: raise ValueError('Still mounted after cleanup')
        finally:
            if directory is not None: os.close(directory)
            os.close(nvme); os.close(candidate)
    after = capture.identity(plan['identity_binding']); capture.verify_backups(plan)
    post = {key:snapshots.block_snapshot(node, capacity, length) for key, node, capacity, length, _ in EXTENTS}
    if before != after or any(post[k]['sha256'] != plan['protected_sha256'][k] for k in ('mbr', 'hfs')):
        raise ValueError('Identity/protected MBR/HFS changed')
    for row in records:
        if capture.full_hash(work/row['saved_as'], row['bytes']) != row['sha256']: raise ValueError('Fresh backup drift')
    result.update(status='installed', run=str(work), identity=after, backups=records, protected_after=post,
        protected_files_sha256=expected, nvme_backups_verified=plan['nvme_backups'],
        nvme_previous_image_sha256=capture.full_hash(work/previous, (work/previous).stat().st_size),
        boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True)
    with (work/'result.json').open('x') as output:
        output.write(json.dumps(result, indent=2)+'\n'); output.flush(); os.fsync(output.fileno())
    return result
