#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Prepare, or explicitly execute, guarded disposable Pi HFS data staging.

No network/media action without --execute and prior physical SD-read success.
Preserves the complete FAT boot span and MBR in a fresh NVMe backup directory.
Writes only the reserved 128-MiB data area, verifies it twice, then publishes
one MBR entry. Never installs a boot image, mounts HFS or reboots the Pi.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import capture_hfs_reference as reference
from check_sd_read_package import sha256
import hfs_stage_core as core
from serial_hfs_read_trial import HFS_LOADER, validate_sd_trial
from serial_sd_read_trial import validate_preflight

ROOT = Path(__file__).resolve().parents[2]
HOST = 'sandrzej@192.168.4.23'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', HOST]


def load_plan(paths):
    snapshots = {name: path.read_bytes() for name, path in paths.items()}
    reports = {name: json.loads(raw) for name, raw in snapshots.items()}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()}
    fixture, baseline, state, preflight = (reports[name] for name in ('fixture', 'baseline', 'sd_trial', 'preflight'))
    reference.validate_fixture(fixture)
    reference.expected_identity(baseline)  # Exact initial card/profile and CSD.
    validate_sd_trial(state, paths['sd_trial'].parent / 'serial.bin', baseline, hashes['baseline'])
    validate_preflight(preflight)
    if (preflight.get('hfs_readonly_trial') is True or state['image_sha256'] != preflight['image_sha256'] or
            HFS_LOADER in Path(preflight['image']).read_bytes()):
        raise ValueError('Passed isolated SD trial must match the current SD-only preflight')
    if any(sha256(path) != hashes[name] for name, path in paths.items()):
        raise ValueError('Staging inputs changed during preflight')
    plan = dict(host=HOST, identity=baseline['identity'], image_sha256=fixture['image_sha256'],
                image_bytes=core.DATA_BYTES, mbr_sha256=baseline['sectors'][0]['sha256'],
                evidence_sha256=hashes, sd_trial_image_sha256=state['image_sha256'],
                protected_boot=dict(start_byte=core.BOOT_START, bytes=core.BOOT_BYTES),
                write_extents=[dict(region='data', start_byte=core.DATA_START, bytes=core.DATA_BYTES),
                               dict(region='mbr', start_byte=0, bytes=512)],
                publication_requires_complete_data_readbacks=2,
                no_hfs_mount=True, no_boot_image_change=True, no_reboot=True,
                scope='Disposable SD fixture preparation only; not XNU HFS acceptance or durability')
    return plan, fixture, hashes


PREPARE = r'''
import json,os,subprocess,tempfile
from pathlib import Path
root=subprocess.check_output(['findmnt','-no','SOURCE,FSTYPE,UUID','/'],text=True,timeout=10).split()
if root!=['/dev/nvme0n1p2','ext4','04570742-280b-43cb-9564-73d454243b1c']:
    raise RuntimeError('Not verified NVMe Linux; no staging directory created')
parent=Path('/home/sandrzej')
if parent.resolve()!=parent or parent.stat().st_dev!=Path('/').stat().st_dev:
    raise RuntimeError('Backup parent is not the verified NVMe filesystem')
space=os.statvfs(parent)
if space.f_bavail*space.f_frsize<1024*1024*1024:
    raise RuntimeError('Need at least 1 GiB free on NVMe for immutable backups and fixture')
run=tempfile.mkdtemp(prefix='xnu-gate4-hfs-stage-',dir=parent)
print(json.dumps(dict(run=run)))
'''

REMOTE = r'''
import fcntl,json,stat,subprocess
from pathlib import Path
def command(*args):
    return subprocess.check_output(args,text=True,timeout=10).strip()
def unmounted(node):
    result=subprocess.run(['findmnt','-rn','-S',node],capture_output=True,text=True,timeout=10)
    if result.returncode!=1 or result.stdout.strip():
        raise RuntimeError('SD is mounted or mount lookup failed: '+node)
def identity():
    root=' '.join(command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split())
    layout=json.loads(command('sfdisk','--json','/dev/mmcblk0'))['partitiontable']
    part=dict(line.split('=',1) for line in command('blkid','-o','export','/dev/mmcblk0p1').splitlines() if '=' in line)
    base=Path('/sys/block/mmcblk0/device')
    card={name:(base/name).read_text().strip() for name in PLAN['identity']['card']}
    result=dict(root=root,layout=layout,partition=part,card=card,
                bytes=int(Path('/sys/block/mmcblk0/size').read_text())*512)
    if result!=PLAN['identity']:
        raise RuntimeError('Fresh root/card/partition identity differs; refusing SD mutation')
    for node in ('/dev/mmcblk0','/dev/mmcblk0p1'):
        unmounted(node)
        holders=Path('/sys/class/block')/Path(node).name/'holders'
        if not holders.is_dir() or any(holders.iterdir()):
            raise RuntimeError('Unknown SD block-device holder')
    if Path('/sys/class/block/mmcblk0p2').exists():
        raise RuntimeError('Kernel already exposes partition 2; refusing stale layout')
    automount=subprocess.run(['systemctl','is-active','--quiet','udisks2','autofs'],timeout=10)
    if automount.returncode not in (3,4):
        raise RuntimeError('Automounter active or service lookup failed; refusing publication')
    return result
def open_regular(path,size=None):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (size is not None and info.st_size!=size):
            raise RuntimeError('Unexpected regular staging input')
        return fd
    except BaseException:
        os.close(fd)
        raise
def open_card(writable):
    fd=os.open('/dev/mmcblk0',(os.O_RDWR if writable else os.O_RDONLY)|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISBLK(info.st_mode) or info.st_rdev!=os.stat('/dev/mmcblk0').st_rdev:
            raise RuntimeError('Card descriptor does not own the verified block device')
        size=struct.unpack('=Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0]
        if size!=CARD_BYTES: raise RuntimeError('Card descriptor capacity differs')
        return fd
    except BaseException:
        os.close(fd)
        raise
def save_bytes(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        write_all(fd,data,0)
        os.fsync(fd)
    finally:
        os.close(fd)
def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
if os.geteuid()!=0: raise RuntimeError('Root required for exact block-device checks')
before=identity()
run=Path(PLAN['run'])
if run.resolve()!=run or not run.is_dir() or run.stat().st_dev!=Path('/').stat().st_dev:
    raise RuntimeError('Backup directory is not a fresh NVMe directory')
if {path.name for path in run.iterdir()}!={'fixture.cdr'}:
    raise RuntimeError('Backup directory is not fresh; never overwrite existing backups')
space=os.statvfs(run)
if space.f_bavail*space.f_frsize<640*1024*1024:
    raise RuntimeError('Insufficient NVMe space for complete boot backup and recovery metadata')
baseline=open_regular('/home/sandrzej/xnu-shell-passed-backup-20261011.bin')
try:
    if hash_span(baseline,0,os.fstat(baseline).st_size)!='bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f':
        raise RuntimeError('Known-good NVMe shell backup differs')
finally: os.close(baseline)
image=open_regular(run/'fixture.cdr',DATA_BYTES)
try:
    if hash_span(image,0,DATA_BYTES)!=PLAN['image_sha256']:
        raise RuntimeError('Transferred fixture differs before SD writes')
    card=open_card(False)
    try:
        original=read_exact(card,512,0)
        updated=plan_mbr(original,PLAN['mbr_sha256'],CARD_BYTES)
        save_bytes(run/'mbr.before.bin',original)
        save_bytes(run/'mbr.planned.bin',updated)
        save_bytes(run/'plan.json',(json.dumps(PLAN,indent=2)+'\n').encode())
        backup=os.open(run/'boot-partition.before.img',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        try: boot_hash=backup_boot(card,backup)
        finally: os.close(backup)
    finally: os.close(card)
    # Both backup files and their directory entry must be durable before the
    # first card write. No NVMe block device or unrelated file is ever opened.
    sync_directory(run)
    sync_directory(run.parent)
    if identity()!=before: raise RuntimeError('Identity changed during backup')
    card=open_card(True)
    try:
        fcntl.flock(card,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if identity()!=before: raise RuntimeError('Identity changed after writable descriptor open')
        result=stage_payload(card,image,original,PLAN['mbr_sha256'],PLAN['image_sha256'],boot_hash)
        fcntl.ioctl(card,0x125f) # BLKRRPART, only after data and MBR readback.
    finally: os.close(card)
finally: os.close(image)
layout=json.loads(command('sfdisk','--json','/dev/mmcblk0'))['partitiontable']
expected=json.loads(json.dumps(PLAN['identity']['layout']))
expected['partitions'].append(dict(node='/dev/mmcblk0p2',start=DATA_START//512,size=DATA_BYTES//512,type='af'))
if layout!=expected: raise RuntimeError('Published partition layout differs; preserve backups')
for node in ('/dev/mmcblk0','/dev/mmcblk0p1','/dev/mmcblk0p2'): unmounted(node)
if (' '.join(command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split())!=before['root'] or
    int(Path('/sys/block/mmcblk0/size').read_text())*512!=before['bytes'] or
    any((Path('/sys/block/mmcblk0/device')/key).read_text().strip()!=value for key,value in before['card'].items()) or
    int(Path('/sys/class/block/mmcblk0p2/start').read_text())!=DATA_START//512 or
    int(Path('/sys/class/block/mmcblk0p2/size').read_text())!=DATA_BYTES//512):
    raise RuntimeError('Root/card/partition range changed after publication; preserve backups')
part=dict(line.split('=',1) for line in command('blkid','-o','export','/dev/mmcblk0p2').splitlines() if '=' in line)
if any(part.get(key)!=value for key,value in dict(TYPE='hfsplus',LABEL='XNU_G4_READ',PARTUUID='5ae1f07e-02').items()):
    raise RuntimeError('Published HFS partition identity differs; preserve backups')
result.update(status='staged',run=str(run),before_identity=before,after_layout=layout,
              mbr_before_hex=original.hex(),image_sha256=PLAN['image_sha256'],
              boot_image_changed=False,hfs_mounted=False,rebooted=False)
save_bytes(run/'result.json',(json.dumps(result,indent=2)+'\n').encode())
sync_directory(run)
print(json.dumps(result))
'''


def remote_source(plan):
    return ('import json\nPLAN=json.loads(' + repr(json.dumps(plan)) + ')\n' +
            Path(core.__file__).read_text() + '\n' + REMOTE)


def validate_result(report, plan):
    old = bytes.fromhex(report['mbr_before_hex'])
    updated = core.plan_mbr(old, plan['mbr_sha256'], core.CARD_BYTES)
    layout = json.loads(json.dumps(plan['identity']['layout']))
    layout['partitions'].append(dict(node='/dev/mmcblk0p2', start=core.DATA_START // 512,
                                     size=core.DATA_BYTES // 512, type='af'))
    required = dict(status='staged', run=plan['run'], before_identity=plan['identity'], after_layout=layout,
                    image_sha256=plan['image_sha256'], mbr_before_sha256=plan['mbr_sha256'],
                    mbr_after_sha256=hashlib.sha256(updated).hexdigest(), boot_partition_bytes=core.BOOT_BYTES,
                    data_start_sector=core.DATA_START // 512, data_sectors=core.DATA_BYTES // 512,
                    data_bytes_written=core.DATA_BYTES, mbr_bytes_written=512,
                    publication_after_two_complete_data_readbacks=True,
                    boot_image_changed=False, hfs_mounted=False, rebooted=False,
                    data_readbacks=[dict(pass_number=n, bytes=core.DATA_BYTES, sha256=plan['image_sha256']) for n in (1, 2)])
    if (any(report.get(key) != value for key, value in required.items()) or
            not re.fullmatch(r'[0-9a-f]{64}', report.get('boot_partition_sha256', '')) or
            any(type(report.get(key)) is not type(value) for key, value in required.items()) or
            any(type(row['pass_number']) is not int or type(row['bytes']) is not int
                for row in report['data_readbacks'])):
        raise ValueError('Incomplete or inconsistent guarded HFS staging result')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'sd-baseline-reference', 'sd-trial', 'preflight', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--execute', action='store_true', help='Actually stage after all guards; default writes only a local plan')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / 'build/rpi5').resolve()):
        parser.error('Put staging evidence in a fresh project build/rpi5 subdirectory')
    paths = dict(fixture=args.fixture, baseline=args.sd_baseline_reference, sd_trial=args.sd_trial, preflight=args.preflight)
    plan, fixture, hashes = load_plan(paths)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(args.output))
        return 0
    # Revalidate immediately before any remote action, not a cached plan flag.
    _, _, fresh_hashes = load_plan(paths)
    if hashes != fresh_hashes:
        raise ValueError('Evidence changed before execution')
    prepared = subprocess.run(SSH + ['python3 -'], input=PREPARE, text=True,
                              capture_output=True, timeout=30, check=True)
    run = json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-stage-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected remote staging directory')
    plan['run'] = run
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    fixture['image'], HOST + ':' + run + '/fixture.cdr'], timeout=300, check=True)
    source = remote_source(plan)
    (args.output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        result = subprocess.run(SSH + ['sudo -n python3 -'], input=source, text=True,
                                capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        # Retain partial diagnostics and the exact remote backup path. A host
        # observation timeout is not proof the remote write has stopped; never
        # retry or roll back automatically after an unknown staging outcome.
        for name, data in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (args.output / name).write_bytes(data.encode() if isinstance(data, str) else data or b'')
        (args.output / 'outcome-unknown.txt').write_text(
            'Remote staging observation timed out; inspect the existing remote run before any retry.\n')
        raise
    (args.output / 'remote.stdout').write_text(result.stdout)
    (args.output / 'remote.stderr').write_text(result.stderr)
    result.check_returncode()
    report = json.loads(result.stdout)
    validate_result(report, plan)
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
