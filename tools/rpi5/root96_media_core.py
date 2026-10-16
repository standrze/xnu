# SPDX-License-Identifier: BSD-2-Clause
"""Exact redundant-file archive/reclaim or single-image stage/restore.

Raw SSD snapshots and verified SSD old-file copies precede every FAT mutation.
The known-good SD backup and normal firmware remain protected in every mode.
No reboot, inferred retry, or automatic rollback.
"""
import json
import os
from pathlib import Path
import re

REDUNDANT='probe.socket-identity-passed-20261012.bin'
RETAINED='probe.socket-identity-pre-pcie-access-20261012.bin'
GOOD_SHA='f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536'
GOOD_BYTES=19384000
FIRMWARE_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
MODES=('root96-reclaim-v1','root96-install-v1','root96-restore-v1')
TEMP={'root96-install-v1':'probe.root96-ssh-20261013.tmp','root96-restore-v1':'probe.root96-restore-20261013.tmp'}


def validate(plan):
    mode=plan.get('profile')
    if mode not in MODES:raise ValueError('Explicit root96 media profile required')
    expected=plan['protected_files']
    if expected.get(RETAINED)!=GOOD_SHA or expected.get('bl31.bin')!=FIRMWARE_SHA:
        raise ValueError('Exact retained zsh backup and normal firmware required')
    for k in ('old_sha256','new_sha256'):
        if not re.fullmatch('[0-9a-f]{64}',plan.get(k,'')):raise ValueError('Exact old/new digests required')
    for k in ('old_bytes','new_bytes'):
        if type(plan.get(k)) is not int or not 0<plan[k]<=32*1024*1024:raise ValueError('Bounded image sizes required')
    if mode=='root96-reclaim-v1':
        if (expected.get(REDUNDANT)!=GOOD_SHA or expected.get('probe.bin')!=GOOD_SHA or
            plan['old_sha256']!=GOOD_SHA or plan['old_bytes']!=GOOD_BYTES or plan['new_sha256']!=GOOD_SHA or plan['new_bytes']!=GOOD_BYTES):
            raise ValueError('Only the exact redundant known-good file may be reclaimed')
    elif expected.get('probe.bin')!=plan['old_sha256'] or plan['old_sha256']==plan['new_sha256']:
        raise ValueError('Current image and distinct replacement required')
    if mode=='root96-install-v1' and (plan['old_sha256']!=GOOD_SHA or plan['old_bytes']!=GOOD_BYTES):
        raise ValueError('Installation must preserve known-good baseline')
    if mode=='root96-restore-v1' and (plan['new_sha256']!=GOOD_SHA or plan['new_bytes']!=GOOD_BYTES):
        raise ValueError('Restoration must return to exact known-good image')


def verify(directory,name,helper,digest,size):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    try:
        if helper.regular(fd)!=size or helper.digest_fd(fd)!=digest:raise ValueError('Exact file differs: '+name)
        return os.fstat(fd)
    finally:os.close(fd)


def absent(directory,name):
    try:os.stat(name,dir_fd=directory,follow_symlinks=False)
    except FileNotFoundError:return
    raise ValueError('Existing/partial artifact; inspect, never retry: '+name)


def journal(work,phase,plan):
    with (work/('media-'+phase+'.json')).open('x') as f:
        json.dump(dict(phase=phase,profile=plan['profile'],old_sha256=plan['old_sha256'],
            new_sha256=plan['new_sha256'],target=REDUNDANT if plan['profile']==MODES[0] else 'probe.bin'),f)
        f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def execute(plan,capture,helper,snapshots,reference,guarded,run=None):
    validate(plan)
    if os.geteuid()!=0:raise ValueError('Root required')
    run=run or guarded.command;mode=plan['profile'];reclaim=mode==MODES[0]
    before=capture.identity(plan['identity_binding']);capture.verify_backups(plan)
    work=Path(plan['run']);expected_names=set() if reclaim else {'candidate.bin'}
    if work.resolve()!=work or work.stat().st_dev!=Path('/').stat().st_dev or {p.name for p in work.iterdir()}!=expected_names:
        raise ValueError('Fresh canonical SSD run required')
    disk=os.statvfs(work)
    if disk.f_bavail*disk.f_frsize<sum(r[3] for r in guarded.EXTENTS)+plan['old_bytes']+1024*1024:
        raise ValueError('Insufficient SSD archive space')
    directory=nvme=candidate=owned=None
    expected=dict(plan['protected_files']);target=REDUNDANT if reclaim else 'probe.bin'
    try:
        nvme=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        if not reclaim:
            candidate=os.open(work/'candidate.bin',os.O_RDONLY|os.O_NOFOLLOW)
            if helper.regular(candidate)!=plan['new_bytes'] or helper.digest_fd(candidate)!=plan['new_sha256']:
                raise ValueError('Candidate differs')
        records=[snapshots.block_snapshot(node,capacity,length,nvme,name) for _,node,capacity,length,name in guarded.EXTENTS]
        if {key:r['sha256'] for (key,*_),r in zip(guarded.EXTENTS,records)}!=plan['protected_sha256']:
            raise ValueError('Full raw baseline differs')
        if capture.identity(plan['identity_binding'])!=before:raise ValueError('Identity changed during snapshots')
        mp=Path(guarded.MOUNTPOINT)
        if mp.resolve()!=mp or not mp.is_dir() or any(mp.iterdir()) or guarded.mount_record(run,required=False) is not None:
            raise ValueError('Empty canonical unmounted FAT path required')
        guarded.invoke(run,['mount','-t','vfat','-o','ro,nosuid,nodev,noexec',guarded.NODE,guarded.MOUNTPOINT])
        owned=guarded.mount_record(run,'ro');directory=os.open(mp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        def guard(access):
            current=guarded.mount_record(run,access)
            if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):raise ValueError('Foreign mount; no cleanup')
            if (os.fstat(directory).st_dev,os.fstat(directory).st_ino)!=(mp.stat().st_dev,mp.stat().st_ino):raise ValueError('Detached mount')
            if (capture.command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split()!=plan['identity_binding']['expected']['root'].split() or
                Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=plan['linux_boot_id']):raise ValueError('SSD root or boot changed')
        guard('ro');files=reference.read_files(directory,expected)
        if not reference.configured_return(files):raise ValueError('Configured autonomous SSD return absent')
        verify(directory,RETAINED,helper,GOOD_SHA,GOOD_BYTES)
        original=verify(directory,target,helper,plan['old_sha256'],plan['old_bytes'])
        if not reclaim:
            absent(directory,TEMP[mode]);space=os.fstatvfs(directory)
            if space.f_bavail*space.f_frsize<plan['new_bytes']+1024*1024:raise ValueError('Insufficient FAT temporary-image space')
        old=os.open(target,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        try:helper.copy_image(old,nvme,'previous.bin',plan['old_sha256']);os.fsync(nvme)
        finally:os.close(old)
        if capture.full_hash(work/'previous.bin',plan['old_bytes'])!=plan['old_sha256']:raise ValueError('SSD old-file archive differs')
        for row in records:
            if capture.full_hash(work/row['saved_as'],row['bytes'])!=row['sha256']:raise ValueError('Complete raw archive drift')
        guard('ro');journal(work,'archives-verified',plan)
        guarded.invoke(run,['mount','-o','remount,rw,nosuid,nodev,noexec',guarded.MOUNTPOINT]);guard('rw')
        reference.read_files(directory,expected);verify(directory,RETAINED,helper,GOOD_SHA,GOOD_BYTES)
        now=verify(directory,target,helper,plan['old_sha256'],plan['old_bytes'])
        if (original.st_dev,original.st_ino)!=(now.st_dev,now.st_ino):raise ValueError('Target file identity changed')
        if reclaim:
            journal(work,'before-exact-unlink',plan);guard('rw')
            os.unlink(REDUNDANT,dir_fd=directory);os.fsync(directory);absent(directory,REDUNDANT)
            del expected[REDUNDANT];journal(work,'after-exact-unlink',plan)
        else:
            helper.copy_image(candidate,directory,TEMP[mode],plan['new_sha256']);os.fsync(directory)
            verify(directory,TEMP[mode],helper,plan['new_sha256'],plan['new_bytes'])
            reference.read_files(directory,expected);verify(directory,RETAINED,helper,GOOD_SHA,GOOD_BYTES)
            journal(work,'before-probe-rename',plan);guard('rw')
            os.rename(TEMP[mode],'probe.bin',src_dir_fd=directory,dst_dir_fd=directory);os.fsync(directory)
            verify(directory,'probe.bin',helper,plan['new_sha256'],plan['new_bytes'])
            expected['probe.bin']=plan['new_sha256'];journal(work,'after-probe-rename',plan)
        guard('rw');reference.read_files(directory,expected)
        guarded.invoke(run,['mount','-o','remount,ro,nosuid,nodev,noexec',guarded.MOUNTPOINT]);guard('ro')
        reference.read_files(directory,expected)
    finally:
        if directory is not None:os.close(directory)
        try:
            if owned is not None:
                current=guarded.mount_record(run)
                if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):raise ValueError('Foreign mount; no cleanup')
                if current['mode']=='rw':
                    guarded.invoke(run,['mount','-o','remount,ro,nosuid,nodev,noexec',guarded.MOUNTPOINT])
                    current=guarded.mount_record(run,'ro')
                    if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):raise ValueError('Foreign mount after remount; no cleanup')
                guarded.invoke(run,['umount',guarded.MOUNTPOINT])
                if guarded.mount_record(run,required=False) is not None:raise ValueError('FAT remains mounted')
        finally:
            if nvme is not None:os.close(nvme)
            if candidate is not None:os.close(candidate)
    after=capture.identity(plan['identity_binding']);capture.verify_backups(plan)
    post={key:snapshots.block_snapshot(node,capacity,length) for key,node,capacity,length,_ in guarded.EXTENTS}
    if before!=after or any(post[k]['sha256']!=plan['protected_sha256'][k] for k in ('mbr','hfs')):
        raise ValueError('Identity or protected MBR/HFS changed')
    for row in records:
        if capture.full_hash(work/row['saved_as'],row['bytes'])!=row['sha256']:raise ValueError('Raw archive drift after mutation')
    if capture.full_hash(work/'previous.bin',plan['old_bytes'])!=plan['old_sha256']:raise ValueError('Old-file archive drift')
    result=dict(status='complete',profile=mode,run=str(work),identity=after,backups=records,protected_after=post,
        protected_files_sha256=expected,nvme_backups_verified=plan['nvme_backups'],archived_file=target,
        previous_file_sha256=plan['old_sha256'],previous_file_bytes=plan['old_bytes'],previous_file_name='previous.bin',
        deleted_files=[REDUNDANT] if reclaim else [],replaced_files=[] if reclaim else ['probe.bin'],
        retained_sd_backup=RETAINED,retained_sd_backup_sha256=GOOD_SHA,firmware_sha256=FIRMWARE_SHA,
        boot_unmounted=True,no_config_change=True,no_firmware_change=True,no_hfs_mount=True,no_reboot=True,
        power_loss_atomicity_claimed=False,no_implicit_retry_or_rollback=True)
    with (work/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    return result
