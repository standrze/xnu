#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit HFS boot-image installation after guarded fixture staging.

Default is local-only. Requires actual SD reads, fresh complete Linux HFS
reference and the successful fixture stager's full FAT/MBR backups. Never
partitions, mounts HFS, changes firmware/configuration or reboots. Unknown
remote outcome requires inspection, never automatic retry or rollback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import capture_hfs_reference as reference
import probe_install_core as core
import serial_hfs_read_trial as trial
import stage_hfs_fixture as fixture_stage

ROOT = Path(__file__).resolve().parents[2]
HOST = fixture_stage.HOST
SSH = fixture_stage.SSH


def load_plan(paths, now=None):
    evidence = {key: paths[key] for key in ('fixture', 'baseline', 'reference', 'preflight', 'sd_trial')}
    reports, hashes = trial.load_inputs(evidence, now=now)
    plan_raw, result_raw = paths['staging_plan'].read_bytes(), paths['staging_result'].read_bytes()
    staged_plan, staged = json.loads(plan_raw), json.loads(result_raw)
    fixture_stage.validate_result(staged, staged_plan)
    if (staged_plan['identity'] != reports['baseline']['identity']
            or staged_plan['image_sha256'] != reports['fixture']['image_sha256']
            or staged['after_layout'] != reports['reference']['identity']['layout']
            or staged_plan.get('sd_trial_image_sha256') != reports['sd_trial']['image_sha256']
            or staged_plan.get('evidence_sha256', {}).get('baseline') != hashes['baseline']
            or staged_plan.get('evidence_sha256', {}).get('sd_trial') != hashes['sd_trial']
            or not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-stage-[a-z0-9_]{8}', staged['run'])):
        raise ValueError('Fixture installation/backups do not bind the accepted SD/HFS evidence')
    hashes.update(staging_plan=hashlib.sha256(plan_raw).hexdigest(),
                  staging_result=hashlib.sha256(result_raw).hexdigest())
    if any(trial.sha256(path) != hashes[key] for key, path in paths.items()):
        raise ValueError('Boot-install evidence changed during validation')
    plan = dict(host=HOST, expected=reports['reference']['identity'],
                fixture_sha256=reports['fixture']['image_sha256'],
                old_image_sha256=reports['sd_trial']['image_sha256'],
                new_image_sha256=reports['preflight']['image_sha256'],
                candidate=reports['preflight']['image'], backup_run=staged['run'],
                boot_backup_sha256=staged['boot_partition_sha256'],
                original_mbr_sha256=staged['mbr_before_sha256'], evidence_sha256=hashes,
                no_hfs_mount=True, no_partition_change=True, no_config_change=True, no_reboot=True)
    return plan


REMOTE = r'''
import contextlib,io,json,os,stat,subprocess
from pathlib import Path
def checked_reference():
    with contextlib.redirect_stdout(io.StringIO()) as output:
        # The reference program uses names such as before/after/fd internally.
        # Isolate it so it cannot overwrite installer state or descriptors.
        exec(REFERENCE_SOURCE,{})
    return json.loads(output.getvalue())
def unmounted(node):
    check=subprocess.run(['findmnt','-rn','-S',node],capture_output=True,text=True,timeout=10)
    if check.returncode!=1 or check.stdout.strip(): raise RuntimeError('SD already mounted or query failed')
def hash_file(path,size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (size is not None and info.st_size!=size):
            raise RuntimeError('Unexpected backup file')
        if info.st_size>536870912: raise RuntimeError('Oversized backup file')
        digest=hashlib.sha256()
        for offset in range(0,info.st_size,CHUNK):
            length=min(CHUNK,info.st_size-offset); data=os.pread(fd,length,offset)
            if len(data)!=length: raise RuntimeError('Short backup read')
            digest.update(data)
        return digest.hexdigest()
    finally: os.close(fd)
if os.geteuid()!=0: raise RuntimeError('Root required')
profile=globals().get('INSTALL_PROFILE','initial')
if profile not in INSTALL_NAMES: raise RuntimeError('Unknown fixed installation profile')
# Full fresh identity + two complete read passes before any SD mount/write.
before=checked_reference()
unmounted('/dev/mmcblk0p1')
for node in ('mmcblk0','mmcblk0p1','mmcblk0p2'):
    holders=Path('/sys/class/block')/node/'holders'
    if not holders.is_dir() or any(holders.iterdir()): raise RuntimeError('Unexpected SD holder')
automount=subprocess.run(['systemctl','is-active','--quiet','udisks2','autofs'],timeout=10)
if automount.returncode not in (3,4): raise RuntimeError('Automounter active or lookup failed')
run=Path(PLAN['run']); backup=Path(PLAN['backup_run'])
for directory in (run,backup):
    if directory.resolve()!=directory or directory.stat().st_dev!=Path('/').stat().st_dev:
        raise RuntimeError('Backup/candidate directory is not verified NVMe')
if {p.name for p in run.iterdir()}!={'candidate.bin'}: raise RuntimeError('Nonfresh installation directory')
if hash_file(backup/'boot-partition.before.img',536870912)!=PLAN['boot_backup_sha256']:
    raise RuntimeError('Complete preserved FAT backup differs')
if hash_file(backup/'mbr.before.bin',512)!=PLAN['original_mbr_sha256']:
    raise RuntimeError('Original MBR backup differs')
if hash_file('/home/sandrzej/xnu-shell-passed-backup-20261011.bin')!='bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f':
    raise RuntimeError('Known-good NVMe shell backup differs')
if profile in ('write-trial','write-diagnostic','write-cache-diagnostic'):
    write_backups=prepare_write_backups(PLAN)
candidate=os.open(run/'candidate.bin',os.O_RDONLY|os.O_NOFOLLOW)
mounted=False; writable=False; directory=None
try:
    if digest_fd(candidate)!=PLAN['new_image_sha256']: raise RuntimeError('Candidate differs')
    mp=Path('/mnt/xnu-probe')
    if not mp.is_dir() or mp.resolve()!=mp: raise RuntimeError('Unexpected boot mountpoint')
    subprocess.run(['mount','-o','ro,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mp)],check=True,timeout=15)
    mounted=True
    if subprocess.check_output(['findmnt','-no','SOURCE,FSTYPE','--target',str(mp)],text=True).split()!=['/dev/mmcblk0p1','vfat']:
        raise RuntimeError('Boot mount is not the exact SD FAT partition')
    expected={'probe.bin':PLAN['old_image_sha256'],
        'probe.shell-passed-20261011.bin':'bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f',
        'probe.gate3-20260927.bin':'454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c',
        'config.txt':'aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28',
        'bl31.bin':'413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46',
        'bcm2712-rpi-5-b.dtb':'e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f'}
    if profile=='statfs-correction':
        expected['probe.sd-read-passed-20261012.bin']=PLAN['passed_sd_image_sha256']
    if profile in ('write-trial','write-diagnostic','write-cache-diagnostic'):
        expected['probe.sd-read-passed-20261012.bin']=PLAN['passed_sd_image_sha256']
        expected['probe.hfs-statfs-failed-20261012.bin']=PLAN['failed_hfs_image_sha256']
    if profile in ('write-diagnostic','write-cache-diagnostic'):
        expected['probe.hfs-read-passed-20261012.bin']=PLAN['readonly_image_sha256']
    if profile=='write-cache-diagnostic':
        expected['probe.hfs-write-no-admission-20261012.bin']=PLAN['no_admission_image_sha256']
    for name,digest in expected.items():
        if hash_file(mp/name)!=digest: raise RuntimeError('Protected/current boot file differs: '+name)
    if profile=='statfs-correction':
        prior=Path(PLAN['prior_boot_run'])
        if prior.resolve()!=prior or prior.stat().st_dev!=Path('/').stat().st_dev:
            raise RuntimeError('Prior boot backup directory is not verified NVMe')
        if hash_file(prior/'sd-read-passed.bin')!=PLAN['passed_sd_image_sha256']:
            raise RuntimeError('Passed SD-only NVMe backup differs')
    if profile in ('write-trial','write-diagnostic','write-cache-diagnostic'):
        for key,name,digest in (('prior_boot_run','sd-read-passed.bin',PLAN['passed_sd_image_sha256']),
                                ('prior_correction_run','hfs-statfs-failed.bin',PLAN['failed_hfs_image_sha256'])):
            prior=Path(PLAN[key])
            if prior.resolve()!=prior or prior.stat().st_dev!=Path('/').stat().st_dev:
                raise RuntimeError('Prior backup directory is not verified NVMe')
            if hash_file(prior/name)!=digest: raise RuntimeError('Prior NVMe backup differs')
    if profile in ('write-diagnostic','write-cache-diagnostic'):
        prior=Path(PLAN['prior_write_run'])
        if prior.resolve()!=prior or prior.stat().st_dev!=Path('/').stat().st_dev:
            raise RuntimeError('Prior write backup directory is not verified NVMe')
        for name,digest in PLAN['prior_write_backup_sha256'].items():
            if name not in ('mbr.before-write.bin','boot-partition.before-write.img','hfs-partition.before.img'):
                raise RuntimeError('Unexpected historical backup name')
            if hash_file(prior/name)!=digest: raise RuntimeError('Prior full write backup differs')
        if hash_file(prior/'hfs-read-passed.bin')!=PLAN['readonly_image_sha256']:
            raise RuntimeError('Passed RO NVMe image differs')
        w1=PLAN['no_admission_image_sha256'] if profile=='write-cache-diagnostic' else PLAN['old_image_sha256']
        if hash_file(prior/'candidate.bin')!=w1:
            raise RuntimeError('Failed write NVMe candidate differs')
    if profile=='write-cache-diagnostic':
        prior=Path(PLAN['prior_cache_run'])
        if prior.resolve()!=prior or prior.stat().st_dev!=Path('/').stat().st_dev:
            raise RuntimeError('Prior cache-probe backup directory is not verified NVMe')
        for name,digest in PLAN['prior_cache_backup_sha256'].items():
            if name not in ('mbr.before-write.bin','boot-partition.before-write.img','hfs-partition.before.img'):
                raise RuntimeError('Unexpected prior cache-probe backup name')
            if hash_file(prior/name)!=digest: raise RuntimeError('Prior cache-probe full backup differs')
        if hash_file(prior/'candidate.bin')!=PLAN['old_image_sha256']:
            raise RuntimeError('Failed cache-probe NVMe candidate differs')
        if hash_file(prior/'hfs-write-no-admission.bin')!=PLAN['no_admission_image_sha256']:
            raise RuntimeError('Preserved W1 NVMe image differs')
    directory=os.open(mp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    old=os.open('probe.bin',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    nvme=os.open(run,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        saved=('hfs-write-cache-probe-failed.bin' if profile=='write-cache-diagnostic' else
               'hfs-write-no-admission.bin' if profile=='write-diagnostic' else
               'hfs-read-passed.bin' if profile=='write-trial' else
               'hfs-statfs-failed.bin' if profile=='statfs-correction' else 'sd-read-passed.bin')
        copy_image(old,nvme,saved,PLAN['old_image_sha256']); os.fsync(nvme)
    finally: os.close(old); os.close(nvme)
    subprocess.run(['mount','-o','remount,rw,nosuid,nodev,noexec',str(mp)],check=True,timeout=15)
    writable=True
    result=install(directory,candidate,PLAN['old_image_sha256'],PLAN['new_image_sha256'],profile)
    subprocess.run(['mount','-o','remount,ro',str(mp)],check=True,timeout=15)
    writable=False
    for name,digest in expected.items():
        wanted=PLAN['new_image_sha256'] if name=='probe.bin' else digest
        if hash_file(mp/name)!=wanted: raise RuntimeError('Post-install protected file differs: '+name)
finally:
    if directory is not None: os.close(directory)
    os.close(candidate)
    if writable: subprocess.run(['mount','-o','remount,ro','/mnt/xnu-probe'],check=True,timeout=15)
    if mounted: subprocess.run(['umount','/mnt/xnu-probe'],check=True,timeout=15)
after=checked_reference()
if before!=after: raise RuntimeError('HFS reference/root/card changed after boot install')
result.update(status='installed',run=str(run),image_sha256=PLAN['new_image_sha256'],
              preserved_sd_image_sha256=PLAN['old_image_sha256'],
              hfs_partition_unchanged=True,protected_boot_files_unchanged=True,
              boot_unmounted=True,no_hfs_mount=True,no_partition_change=True,no_config_change=True,no_reboot=True)
if profile in ('write-trial','write-diagnostic','write-cache-diagnostic'):
    result['write_trial_backups']=finish_write_install(PLAN,write_backups)
with (run/'result.json').open('x') as output:
    output.write(json.dumps(result,indent=2)+'\n'); output.flush(); os.fsync(output.fileno())
print(json.dumps(result))
'''


def remote_source(plan):
    source = reference.remote_source(plan['expected'], plan['fixture_sha256'])
    return ('import json\nPLAN=json.loads(' + repr(json.dumps(plan)) + ')\n'
            + 'REFERENCE_SOURCE=' + repr(source) + '\n' + Path(core.__file__).read_text() + '\n' + REMOTE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = dict(fixture='fixture', baseline='sd-baseline-reference', reference='reference',
                 preflight='preflight', sd_trial='sd-trial', staging_plan='staging-plan', staging_result='staging-result')
    for flag in (*flags.values(), 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / 'build/rpi5').resolve()):
        parser.error('Use a fresh build/rpi5 output directory')
    paths = {key: getattr(args, flag.replace('-', '_')) for key, flag in flags.items()}
    plan = load_plan(paths)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(args.output))
        return 0
    if load_plan(paths) != plan:
        raise ValueError('Installation evidence changed before execution')
    prepare = fixture_stage.PREPARE.replace("prefix='xnu-gate4-hfs-stage-'", "prefix='xnu-gate4-hfs-boot-'")
    response = subprocess.run(SSH + ['python3 -'], input=prepare, text=True, capture_output=True,
                              check=True, timeout=30)
    run = json.loads(response.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-boot-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected NVMe installation directory')
    plan['run'] = run
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    plan['candidate'], HOST + ':' + run + '/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (args.output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        response = subprocess.run(SSH + ['sudo -n python3 -'], input=source, text=True,
                                  capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, data in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (args.output / name).write_bytes(data.encode() if isinstance(data, str) else data or b'')
        (args.output / 'outcome-unknown.txt').write_text('Inspect the existing remote run; never automatically retry or roll back.\n')
        raise
    (args.output / 'remote.stdout').write_text(response.stdout)
    (args.output / 'remote.stderr').write_text(response.stderr)
    response.check_returncode()
    result = json.loads(response.stdout)
    required = dict(status='installed',run=run,image_sha256=plan['new_image_sha256'],
                    preserved_sd_image_sha256=plan['old_image_sha256'],hfs_partition_unchanged=True,
                    protected_boot_files_unchanged=True,boot_unmounted=True,no_hfs_mount=True,
                    no_partition_change=True,no_config_change=True,no_reboot=True)
    if any(result.get(key) != value or type(result.get(key)) is not type(value) for key,value in required.items()):
        raise ValueError('Incomplete boot-install result; inspect existing run')
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
