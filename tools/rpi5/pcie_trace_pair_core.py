# SPDX-License-Identifier: BSD-2-Clause
"""Distinct RP1 trace pair profile; exact retained FAT backup and SSD-only trial archive.

All backups and both temporary files are verified before the first rename.
Publication is firmware first, loader second, with a durable NVMe journal.
The caller supplies the unchanged exact-card/mount/block/copy helpers.
"""
import json
import os
from pathlib import Path
import re

NAMES={
    'pcie-trace-pair-trial-v1':{
        'bl31.bin':('bl31.pre-rp1trace-20261013.bin','bl31.rp1trace-20261013.tmp','firmware-before.bin'),
        'probe.bin':('probe.socket-identity-pre-pcie-access-20261012.bin','probe.rp1trace-20261013.tmp','loader-before.bin')},
    'pcie-trace-pair-restore-v1':{
        'bl31.bin':('bl31.rp1trace-trial-20261013.bin','bl31.post-rp1trace-20261013.tmp','firmware-trial.bin'),
        'probe.bin':(None,'probe.post-rp1trace-20261013.tmp','loader-trial.bin')},
}
TARGETS=('bl31.bin','probe.bin')
REUSED_ZSH_BACKUP='probe.socket-identity-pre-pcie-access-20261012.bin'
GOOD_ZSH_SHA='f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536'
GOOD_ZSH_BYTES=19384000


def reuse_backup(plan,row):
    return plan['profile']=='pcie-trace-pair-trial-v1' and row['target']=='probe.bin'


def ssd_only_backup(plan,row):
    return plan['profile']=='pcie-trace-pair-restore-v1' and row['target']=='probe.bin'


def fat_space_required(plan):
    validate_files(plan)
    return sum(r['new_bytes']+(0 if reuse_backup(plan,r) or ssd_only_backup(plan,r) else r['old_bytes']) for r in plan['files'])+1024*1024


def validate_files(plan):
    if plan.get('profile') not in NAMES or not isinstance(plan.get('files'),list) or len(plan['files'])!=2:
        raise ValueError('Explicit fixed firmware-pair profile required')
    if plan.get('protected_files',{}).get(REUSED_ZSH_BACKUP)!=GOOD_ZSH_SHA:
        raise ValueError('Exact known-good retained SD backup required in both transitions')
    for target,row in zip(TARGETS,plan['files']):
        if not isinstance(row,dict) or set(row)!={'target','candidate','old_sha256','new_sha256','old_bytes','new_bytes'}:
            raise ValueError('Exact pair row required')
        if row['target']!=target or row['candidate']!='candidate-'+target:raise ValueError('Fixed pair order/names required')
        if any(not isinstance(row[k],str) or not re.fullmatch('[0-9a-f]{64}',row[k]) for k in ('old_sha256','new_sha256')):
            raise ValueError('Exact pair digests required')
        if row['old_sha256']==row['new_sha256']:raise ValueError('Both fixed files must make distinct transitions')
        if any(type(row[k]) is not int or not 0<row[k]<=32*1024*1024 for k in ('old_bytes','new_bytes')):
            raise ValueError('Bounded pair sizes required')
        if reuse_backup(plan,row) and plan.get('protected_files',{}).get(REUSED_ZSH_BACKUP)!=row['old_sha256']:
            raise ValueError('Reused backup must be the exact already protected old loader')


def journal(work,phase,plan):
    # New, never overwritten, fsynced on SSD before/after each publication.
    path=work/('pair-'+phase+'.json')
    with path.open('x') as out:
        out.write(json.dumps(dict(phase=phase,profile=plan['profile'],files=plan['files']),sort_keys=True)+'\n')
        out.flush();os.fsync(out.fileno())
    directory=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory)
    finally:os.close(directory)


def read_image(directory,name,helper,expected,size):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    try:
        if helper.regular(fd)!=size or helper.digest_fd(fd)!=expected:raise ValueError('Pair file differs: '+name)
    finally:os.close(fd)


def absent_artifacts(directory,plan,helper):
    read_image(directory,REUSED_ZSH_BACKUP,helper,GOOD_ZSH_SHA,GOOD_ZSH_BYTES)
    for row in plan['files']:
        backup,temporary,_=NAMES[plan['profile']][row['target']]
        if reuse_backup(plan,row):
            # This existing file is an input, never a copy/rename/remove target.
            # Verify both size and complete digest before any FAT write.
            read_image(directory,backup,helper,row['old_sha256'],row['old_bytes'])
            names=(temporary,)
        else:names=(temporary,) if ssd_only_backup(plan,row) else (backup,temporary)
        for name in names:
            try:os.stat(name,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:continue
            raise ValueError('Partial/existing pair artifact; inspect, never retry: '+name)


def publish(directory,candidates,plan,helper,guard,work,reference):
    validate_files(plan);names=NAMES[plan['profile']]
    # Refuse every stale/partial destination before any SD write.
    absent_artifacts(directory,plan,helper)
    for row in plan['files']:
        target=row['target'];backup,temporary,_=names[target];guard('rw')
        if helper.regular(candidates[target])!=row['new_bytes'] or helper.digest_fd(candidates[target])!=row['new_sha256']:
            raise ValueError('Pair candidate changed')
        old=os.open(target,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        try:
            if helper.regular(old)!=row['old_bytes'] or helper.digest_fd(old)!=row['old_sha256']:
                raise ValueError('Current pair changed')
            if reuse_backup(plan,row):
                read_image(directory,backup,helper,row['old_sha256'],row['old_bytes'])
            elif not ssd_only_backup(plan,row):
                helper.copy_image(old,directory,backup,row['old_sha256']);os.fsync(directory)
        finally:os.close(old)
        guard('rw');helper.copy_image(candidates[target],directory,temporary,row['new_sha256']);os.fsync(directory)
    expected=dict(plan['protected_files'],**{r['target']:r['old_sha256'] for r in plan['files']})
    guard('rw');reference.read_files(directory,expected)
    for row in plan['files']:
        if not ssd_only_backup(plan,row):read_image(directory,names[row['target']][0],helper,row['old_sha256'],row['old_bytes'])
        read_image(directory,names[row['target']][1],helper,row['new_sha256'],row['new_bytes'])
    journal(work,'prepared',plan)
    published=[]
    for row in plan['files']:
        target=row['target'];guard('rw')
        # Also recheck the other protected files/current half of the pair.
        reference.read_files(directory,expected)
        read_image(directory,names[target][1],helper,row['new_sha256'],row['new_bytes'])
        if helper.digest_fd(candidates[target])!=row['new_sha256']:raise ValueError('Candidate changed before rename')
        journal(work,'before-'+target,plan);guard('rw')
        os.rename(names[target][1],target,src_dir_fd=directory,dst_dir_fd=directory);os.fsync(directory)
        guard('rw');read_image(directory,target,helper,row['new_sha256'],row['new_bytes'])
        journal(work,'after-'+target,plan);published.append(target)
        expected[target]=row['new_sha256']
    return dict(pair_publication_order=published,temporary_pair_published=True,
        reused_existing_sd_backups={NAMES[plan['profile']][r['target']][0]:r['old_sha256'] for r in plan['files'] if reuse_backup(plan,r)},
        power_loss_atomicity_claimed=False,no_implicit_rollback=True,
        preserved_pair={r['target']:dict(sha256=r['old_sha256'],bytes=r['old_bytes'],
            sd_backup=names[r['target']][0],nvme_backup=names[r['target']][2]) for r in plan['files']},
        pair_sha256={r['target']:r['new_sha256'] for r in plan['files']})


def execute(plan,capture,helper,snapshots,reference,guarded,run=None):
    validate_files(plan)
    if os.geteuid()!=0:raise ValueError('Root required for exact pair installation')
    run=run or guarded.command
    before=capture.identity(plan['identity_binding']);capture.verify_backups(plan)
    work=Path(plan['run']);candidate_names={r['candidate'] for r in plan['files']}
    if work.resolve()!=work or work.stat().st_dev!=Path('/').stat().st_dev or {p.name for p in work.iterdir()}!=candidate_names:
        raise ValueError('Fresh canonical NVMe pair run required')
    space=os.statvfs(work)
    need=sum(r[3] for r in guarded.EXTENTS)+sum(r['old_bytes'] for r in plan['files'])+1024*1024
    if space.f_bavail*space.f_frsize<need:raise ValueError('Insufficient SSD space for complete raw and pair backups')
    candidates={};nvme=directory=owned=None
    try:
        for row in plan['files']:
            fd=os.open(work/row['candidate'],os.O_RDONLY|os.O_NOFOLLOW);candidates[row['target']]=fd
            if os.fstat(fd).st_dev!=work.stat().st_dev or helper.regular(fd)!=row['new_bytes'] or helper.digest_fd(fd)!=row['new_sha256']:
                raise ValueError('Pair candidate differs')
        nvme=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        records=[snapshots.block_snapshot(node,capacity,length,nvme,name)
            for _,node,capacity,length,name in guarded.EXTENTS]
        if {key:r['sha256'] for (key,*_),r in zip(guarded.EXTENTS,records)}!=plan['protected_sha256']:
            raise ValueError('Complete MBR/FAT/HFS baseline differs')
        if capture.identity(plan['identity_binding'])!=before:raise ValueError('Identity changed during snapshots')
        mp=Path(guarded.MOUNTPOINT)
        if mp.resolve()!=mp or not mp.is_dir() or any(mp.iterdir()) or guarded.mount_record(run,required=False) is not None:
            raise ValueError('Empty unmounted canonical FAT mountpoint required')
        guarded.invoke(run,['mount','-t','vfat','-o','ro,nosuid,nodev,noexec',guarded.NODE,guarded.MOUNTPOINT])
        owned=guarded.mount_record(run,'ro')
        directory=os.open(mp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        def guard(mode):
            current=guarded.mount_record(run,mode)
            if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):
                raise ValueError('Mount ownership changed; no foreign cleanup')
            if (os.fstat(directory).st_dev,os.fstat(directory).st_ino)!=(mp.stat().st_dev,mp.stat().st_ino):
                raise ValueError('Mount descriptor detached')
            if (capture.command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split()!=plan['identity_binding']['expected']['root'].split() or
                Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=plan['linux_boot_id']):
                raise ValueError('SSD root or boot changed')
        expected=dict(plan['protected_files'],**{r['target']:r['old_sha256'] for r in plan['files']})
        guard('ro');files=reference.read_files(directory,expected)
        if not reference.configured_return(files):raise ValueError('Configured autonomous SSD return absent')
        absent_artifacts(directory,plan,helper)
        space=os.fstatvfs(directory)
        need=fat_space_required(plan)
        if space.f_bavail*space.f_frsize<need:raise ValueError('Insufficient FAT space for both backups and temporaries')
        for row in plan['files']:
            old=os.open(row['target'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            try:
                if helper.regular(old)!=row['old_bytes'] or helper.digest_fd(old)!=row['old_sha256']:raise ValueError('Old pair changed')
                helper.copy_image(old,nvme,NAMES[plan['profile']][row['target']][2],row['old_sha256']);os.fsync(nvme)
            finally:os.close(old)
        for row in plan['files']:
            if capture.full_hash(work/NAMES[plan['profile']][row['target']][2],row['old_bytes'])!=row['old_sha256']:
                raise ValueError('NVMe pair backup differs')
        guard('ro');guarded.invoke(run,['mount','-o','remount,rw,nosuid,nodev,noexec',guarded.MOUNTPOINT])
        guard('rw');result=publish(directory,candidates,plan,helper,guard,work,reference)
        guard('rw');guarded.invoke(run,['mount','-o','remount,ro,nosuid,nodev,noexec',guarded.MOUNTPOINT]);guard('ro')
        for row in plan['files']:
            expected[row['target']]=row['new_sha256']
            if not ssd_only_backup(plan,row):expected[NAMES[plan['profile']][row['target']][0]]=row['old_sha256']
        reference.read_files(directory,expected);guard('ro')
    finally:
        if directory is not None:os.close(directory);directory=None
        try:
            if owned is not None:
                current=guarded.mount_record(run)
                if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):raise ValueError('Mount replaced; no foreign cleanup')
                if current['mode']=='rw':
                    guarded.invoke(run,['mount','-o','remount,ro,nosuid,nodev,noexec',guarded.MOUNTPOINT])
                    current=guarded.mount_record(run,'ro')
                    if any(current[k]!=owned[k] for k in ('id','source','fstype','target')):raise ValueError('Mount changed during cleanup')
                guarded.invoke(run,['umount',guarded.MOUNTPOINT])
                if guarded.mount_record(run,required=False) is not None:raise ValueError('Still mounted')
        finally:
            if nvme is not None:os.close(nvme)
            for fd in candidates.values():os.close(fd)
    after=capture.identity(plan['identity_binding']);capture.verify_backups(plan)
    post={key:snapshots.block_snapshot(node,capacity,length) for key,node,capacity,length,_ in guarded.EXTENTS}
    if before!=after or any(post[k]['sha256']!=plan['protected_sha256'][k] for k in ('mbr','hfs')):
        raise ValueError('Identity or protected MBR/HFS changed')
    for row in records:
        if capture.full_hash(work/row['saved_as'],row['bytes'])!=row['sha256']:raise ValueError('Fresh raw snapshot drift')
    result.update(status='installed',run=str(work),identity=after,backups=records,protected_after=post,
        protected_files_sha256=expected,nvme_backups_verified=plan['nvme_backups'],boot_unmounted=True,
        no_hfs_mount=True,no_config_change=True,no_reboot=True,firmware_changed=True,
        nvme_previous_pair_sha256={r['target']:capture.full_hash(work/NAMES[plan['profile']][r['target']][2],r['old_bytes']) for r in plan['files']})
    with (work/'result.json').open('x') as out:
        out.write(json.dumps(result,indent=2)+'\n');out.flush();os.fsync(out.fileno())
    return result


