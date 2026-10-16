#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate exact-backup reclaim, combined-image install, or explicit restore."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_fw_reuse_trial as firmware
import root96_media_core as core
import check_root96_ssh_package as package
import rpi5_board_lease as lease

ROOT,HOST,SSH,sha=firmware.ROOT,firmware.HOST,firmware.SSH,firmware.sha
base=firmware.base
MODES={'reclaim':core.MODES[0],'install':core.MODES[1],'restore':core.MODES[2]}


def source_pins():
    paths=(Path(__file__),Path(core.__file__),Path(package.__file__),Path(lease.__file__),
        *(Path(m.__file__) for m in base.MODULES),Path(firmware.__file__),
        ROOT/'tools/rpi5/root96_trial_core.py',ROOT/'tools/rpi5/serial_root96_trial.py',
        ROOT/'tools/rpi5/audit_root96_trial.py',
        ROOT/'tools/rpi5/audit_socket_identity_trial.py',ROOT/'tools/rpi5/capture_pcie_fw_reuse_linux_return.py',
        ROOT/'tools/rpi5/tests/test_root96_trial.py')
    return {str(p.resolve()):sha(p) for p in paths}


def inherited(plan,result,count):
    rows=copy.deepcopy(plan['nvme_backups'])
    rows.extend(dict(path=result['run']+'/'+r['saved_as'],bytes=r['bytes'],sha256=r['sha256']) for r in result['backups'])
    rows.append(dict(path=result['run']+'/previous.bin',bytes=plan['old_bytes'],sha256=plan['old_sha256']))
    if len(rows)!=count or len({r['path'] for r in rows})!=count:raise ValueError('Incomplete new media backup chain')
    return rows


def load_plan(operation,boot,baseline,candidate_package=None):
    if operation not in MODES or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):
        raise ValueError('Explicit operation and fresh SSD Linux UUID required')
    baseline=baseline.resolve()
    if baseline.parent!=ROOT/'build/rpi5':raise ValueError('Exact local baseline receipt required')
    previous=json.loads((baseline/'plan.json').read_text());result=json.loads((baseline/'result.json').read_text())
    if operation=='reclaim':
        firmware.validate_result(result,previous)
        if previous['profile']!='firmware-abi-reuse-restore':raise ValueError('Completed normal-firmware/zsh restoration required')
        rows=firmware.inherited_pair(previous,result,70)
        oldhash=newhash=core.GOOD_SHA;oldbytes=newbytes=core.GOOD_BYTES;candidate=None;preflight=None
    else:
        validate_result(result,previous)
        expected='root96-reclaim-v1' if operation=='install' else 'root96-install-v1'
        if previous['profile']!=expected:raise ValueError('Wrong exact preceding media transition')
        rows=inherited(previous,result,74 if operation=='install' else 78)
        if operation=='install':
            if candidate_package is None:raise ValueError('Exact combined package required')
            preflight=package.inspect(candidate_package)
            candidate=preflight['image'];oldhash=core.GOOD_SHA;oldbytes=core.GOOD_BYTES
            newhash=preflight['image_sha256'];newbytes=preflight['image_bytes']
        else:
            preflight=base.socket_package.inspect(base.SOCKET)
            candidate=preflight['image'];oldhash=previous['new_sha256'];oldbytes=previous['new_bytes']
            newhash=core.GOOD_SHA;newbytes=core.GOOD_BYTES
    for name,pin in previous['source_sha256'].items():
        if sha(baseline/'source-snapshots'/Path(name).name)!=pin:raise ValueError('Archived prior operation source differs')
    binding=copy.deepcopy(previous['identity_binding'])
    if boot!=result['identity']['boot_id']:binding['linux_boot_id_before_write']=result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot
    if binding['linux_boot_id_before_write']==boot:raise ValueError('Missing distinct Linux boot witness')
    plan=dict(host=HOST,operation=operation,profile=MODES[operation],linux_boot_id=boot,identity_binding=binding,
        nvme_backups=rows,protected_sha256={k:r['sha256'] for k,r in result['protected_after'].items()},
        protected_files=result['protected_files_sha256'],old_sha256=oldhash,new_sha256=newhash,
        old_bytes=oldbytes,new_bytes=newbytes,candidate=candidate,preflight=preflight,
        package=str(candidate_package.resolve()) if candidate_package else None,
        ancestry=dict(directory=str(baseline),hashes={n:sha(baseline/n) for n in ('plan.json','result.json')}),
        source_sha256=source_pins(),no_firmware_change=True,no_config_change=True,no_hfs_mount=True,no_reboot=True,
        no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
    core.validate(plan)
    return plan


def validate_result(result,plan):
    core.validate(plan)
    expected_plan=load_plan(plan['operation'],plan['linux_boot_id'],Path(plan['ancestry']['directory']),
        Path(plan['package']) if plan['package'] else None)
    if not base.reference.same({k:v for k,v in plan.items() if k!='run'},expected_plan):raise ValueError('Media plan ancestry differs')
    reclaim=plan['operation']=='reclaim';files=dict(plan['protected_files'])
    if reclaim:del files[core.REDUNDANT]
    else:files['probe.bin']=plan['new_sha256']
    required=dict(status='complete',profile=plan['profile'],run=plan['run'],
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
        protected_files_sha256=files,nvme_backups_verified=plan['nvme_backups'],
        archived_file=core.REDUNDANT if reclaim else 'probe.bin',previous_file_name='previous.bin',
        previous_file_sha256=plan['old_sha256'],previous_file_bytes=plan['old_bytes'],
        deleted_files=[core.REDUNDANT] if reclaim else [],replaced_files=[] if reclaim else ['probe.bin'],
        retained_sd_backup=core.RETAINED,retained_sd_backup_sha256=core.GOOD_SHA,firmware_sha256=core.FIRMWARE_SHA,
        boot_unmounted=True,no_config_change=True,no_firmware_change=True,no_hfs_mount=True,no_reboot=True,
        power_loss_atomicity_claimed=False,no_implicit_retry_or_rollback=True,
        backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
            for key,node,_,length,name in base.core.EXTENTS])
    if any(not base.reference.same(result.get(k),v) for k,v in required.items()):raise ValueError('Incomplete media receipt')
    if set(result.get('protected_after',{}))!={'mbr','boot','hfs'}:raise ValueError('Incomplete post-operation raw extents')
    for key,node,_,length,_ in base.core.EXTENTS:
        row=result['protected_after'][key]
        if row.get('device')!=node or type(row.get('bytes')) is not int or row['bytes']!=length or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):
            raise ValueError('Post-operation extent shape differs')
        if key!='boot' and row['sha256']!=plan['protected_sha256'][key]:raise ValueError('Protected MBR/HFS changed')


def remote_source(plan):
    if source_pins()!=plan['source_sha256']:raise ValueError('Media tool sources changed')
    core.validate(plan);source='import types,json\n'
    for name,module in zip(('capture','helper','snapshots','reference','guarded','media'),(*base.MODULES,core)):
        source+=f'{name}=types.ModuleType({name!r})\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(media.execute(PLAN,capture,helper,snapshots,reference,guarded)))\n'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=MODES)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--linux-boot-id',required=True)
    p.add_argument('--package',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    with lease.hold(ROOT,'root96-media-'+args.operation):
        out=args.output.resolve()
        if out.parent!=ROOT/'build/rpi5':raise ValueError('Fresh local evidence directory required')
        plan=load_plan(args.operation,args.linux_boot_id,args.baseline,args.package);out.mkdir(exist_ok=False)
        archive=out/'source-snapshots';archive.mkdir()
        for name,pin in plan['source_sha256'].items():
            target=archive/Path(name).name;shutil.copyfile(name,target)
            if sha(target)!=pin:raise ValueError('Archived current source differs')
        def save():(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        save()
        if not args.execute:print('LOCAL_ROOT96_MEDIA_PLAN '+str(out));return 0
        if load_plan(args.operation,args.linux_boot_id,args.baseline,args.package)!=plan:raise ValueError('Media inputs changed')
        prepare=base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-root96-'")
        r=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
        work=json.loads(r.stdout)['run']
        if not re.fullmatch('/home/sandrzej/xnu-root96-[a-z0-9_]{8}',work):raise ValueError('Unexpected SSD run')
        plan['run']=work;save()
        if plan['candidate']:
            subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                plan['candidate'],HOST+':'+work+'/candidate.bin'],check=True,timeout=60)
        source=remote_source(plan);(out/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
        try:r=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
        except subprocess.TimeoutExpired as error:
            for name,data in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
                (out/name).write_bytes(data.encode() if isinstance(data,str) else data or b'')
            (out/'outcome-unknown.txt').write_text('Inspect exact SSD run, journal and mount. No retry or inferred rollback.\n');raise
        (out/'remote.stdout').write_text(r.stdout);(out/'remote.stderr').write_text(r.stderr)
        r.check_returncode();result=json.loads(r.stdout);validate_result(result,plan)
        if source_pins()!=plan['source_sha256']:raise ValueError('Media source changed during operation')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out);return 0


if __name__=='__main__':raise SystemExit(main())
