#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Inspect/finalize the one published trial whose open directory blocked unmount.

Never reinstall, remount RW, reboot or restore. Uses its exact archived helpers.
Default is local source verification only; execute adopts only inspected RO
mount ID 88 on the exact card, rechecks every artifact, then unmounts once.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_watchdog_recovery_trial as staging

DIRECTORY = staging.ROOT/'build/rpi5/watchdog-recovery-installed-20261012'
RUN = '/home/sandrzej/xnu-gate5-watchdog-uz9c99br'

REMOTE = r'''
if PLAN['profile']!='watchdog-only-trial' or PLAN['run']!=EXPECTED_RUN: raise ValueError('Exact failed run required')
work=Path(PLAN['run'])
if work.resolve()!=work or work.stat().st_dev!=Path('/').stat().st_dev: raise ValueError('Not exact SSD run')
if {p.name for p in work.iterdir()}!={'candidate.bin','mbr.before-write.bin','boot-partition.before-write.img',
    'hfs-partition.before.img','socket-identity-passed.bin'}: raise ValueError('Unexpected partial-run files; inspect only')
expected=PLAN['identity_binding']['expected']
if capture.command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split()!=expected['root'].split(): raise ValueError('SSD root changed')
if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=PLAN['linux_boot_id']: raise ValueError('Boot changed')
card=Path('/sys/block/mmcblk0/device')
if {k:(card/k).read_text().strip() for k in ('cid','csd')}!=expected['card']: raise ValueError('Card changed')
if json.loads(capture.command('sfdisk','--json','/dev/mmcblk0'))['partitiontable']!=expected['layout']: raise ValueError('Layout changed')
owned=trial.mount_record(trial.command,'ro')
if owned['id']!=88: raise ValueError('Inspected RO mount replaced; no cleanup')
capture.verify_backups(PLAN)
records=[]
for key,node,capacity,length,name in trial.EXTENTS:
    pin=PLAN['protected_sha256'][key]
    if capture.full_hash(work/name,length)!=pin: raise ValueError('Fresh complete snapshot differs')
    records.append(dict(device=node,bytes=length,sha256=pin,saved_as=name))
if capture.full_hash(work/'candidate.bin',38592)!=PLAN['new_image_sha256']: raise ValueError('Candidate changed')
if capture.full_hash(work/'socket-identity-passed.bin',19384000)!=PLAN['old_image_sha256']: raise ValueError('Working image backup differs')
files=dict(PLAN['protected_files'],**{'probe.bin':PLAN['new_image_sha256'],
    'probe.socket-identity-passed-20261012.bin':PLAN['old_image_sha256']})
directory=os.open(trial.MOUNTPOINT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    observed=reference.read_files(directory,files)
    if not reference.configured_return(observed): raise ValueError('Configured return absent')
    if trial.mount_record(trial.command,'ro')!=owned: raise ValueError('RO mount changed during audit')
finally: os.close(directory)
# This explicit inspected cleanup is not an install retry. All SD FDs are now
# closed. No remount, file publication or rollback path exists in this program.
if trial.mount_record(trial.command,'ro')!=owned: raise ValueError('RO mount replaced before cleanup')
trial.invoke(trial.command,['umount',trial.MOUNTPOINT])
if trial.mount_record(trial.command,required=False) is not None: raise ValueError('Still mounted')
after=capture.identity(PLAN['identity_binding']); capture.verify_backups(PLAN)
post={key:snapshots.block_snapshot(node,capacity,length) for key,node,capacity,length,_ in trial.EXTENTS}
if any(post[k]['sha256']!=PLAN['protected_sha256'][k] for k in ('mbr','hfs')): raise ValueError('Protected raw extents differ')
result=dict(status='installed',run=EXPECTED_RUN,image_sha256=PLAN['new_image_sha256'],
    preserved_sd_image_sha256=PLAN['old_image_sha256'],nvme_previous_image_sha256=PLAN['old_image_sha256'],
    sd_backup='probe.socket-identity-passed-20261012.bin',temporary_published=True,power_loss_atomicity_claimed=False,
    identity=after,backups=records,protected_after=post,protected_files_sha256=files,
    nvme_backups_verified=PLAN['nvme_backups'],boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,
    inspected_post_publication_cleanup=True,adopted_readonly_mount=owned,
    cleanup_reason='Original open directory descriptor kept Linux mount busy; no install retry')
with (work/'result.json').open('x') as output:
    output.write(json.dumps(result,indent=2)+'\n');output.flush();os.fsync(output.fileno())
print(json.dumps(result))
'''


def program():
    plan = json.loads((DIRECTORY/'plan.json').read_text())
    if plan['run'] != RUN or plan['new_image_sha256'] != staging.IMAGE_SHA or plan['old_image_sha256'] != staging.prior.NEW_SHA:
        raise ValueError('Exact published run required')
    archived = DIRECTORY/'source-snapshots'
    for name,pin in plan['source_sha256'].items():
        if staging.sha(archived/Path(name).name) != pin: raise ValueError('Original source snapshot changed')
    source = 'import types,json,os\nfrom pathlib import Path\n'
    for name, module in zip(('capture','helper','snapshots','reference','trial'), staging.MODULES):
        text = (archived/Path(module.__file__).name).read_text()
        source += f'{name}=types.ModuleType({name!r})\nexec('+repr(text)+f',{name}.__dict__)\n'
    source += 'PLAN=json.loads('+repr(json.dumps(plan))+')\nEXPECTED_RUN='+repr(RUN)+'\n'+REMOTE
    compile(source,'<inspected-finalize>','exec')
    return plan,source


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    plan,source=program()
    if not args.execute: print('LOCAL_INSPECTION_PLAN_NO_NETWORK'); return 0
    if (DIRECTORY/'result.json').exists(): raise ValueError('Already finalized; no retry')
    # Retain both original failed output/source and this explicit cleanup.
    with (DIRECTORY/'finalize-source.py').open('x') as output: output.write(source)
    try:
        response=subprocess.run(staging.SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=180)
    except subprocess.TimeoutExpired as error:
        for name,value in (('finalize.stdout',error.stdout),('finalize.stderr',error.stderr)):
            (DIRECTORY/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (DIRECTORY/'finalize-outcome-unknown.txt').write_text('Inspect the same run/mount. Never reinstall, reboot or repeat finalization blindly.\n')
        raise
    (DIRECTORY/'finalize.stdout').write_text(response.stdout); (DIRECTORY/'finalize.stderr').write_text(response.stderr)
    response.check_returncode(); result=json.loads(response.stdout); staging.validate_result(result,plan)
    with (DIRECTORY/'result.json').open('x') as output: output.write(json.dumps(result,indent=2)+'\n')
    print(DIRECTORY); return 0


if __name__=='__main__': raise SystemExit(main())
