#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit exact-card RP1-ID dual firmware/kernel trial or pair restoration."""
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
import stage_root96_trial as prior
import pcie_id_pair_core as core
import check_pcie_id_trial_package as package
import rpi5_board_lease as lease

ROOT,HOST,SSH,sha,base=prior.ROOT,prior.HOST,prior.SSH,prior.sha,prior.base
OLD_FIRMWARE=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
OLD_FW_SHA=prior.core.FIRMWARE_SHA
TRIAL='pcie-id-pair-trial-v1'
RESTORE='pcie-id-pair-restore-v1'


def source_pins():
    paths=(Path(__file__),Path(core.__file__),Path(package.__file__),Path(prior.__file__),Path(lease.__file__),
        *(Path(m.__file__) for m in base.MODULES),
        *(ROOT/'tools/rpi5'/n for n in ('serial_pcie_id_trial.py','pcie_id_serial_core.py',
            'pcie_id_evidence.py','capture_pcie_id_linux_return.py','capture_pcie_id_failed_return.py',
            'tests/test_pcie_id_trial.py')))
    return {str(p.resolve()):sha(p) for p in paths}


def inherited(plan,result,count):
    rows=copy.deepcopy(plan['nvme_backups'])
    rows.extend(dict(path=result['run']+'/'+r['saved_as'],bytes=r['bytes'],sha256=r['sha256']) for r in result['backups'])
    rows.extend(dict(path=result['run']+'/'+core.NAMES[plan['profile']][r['target']][2],
        bytes=r['old_bytes'],sha256=r['old_sha256']) for r in plan['files'])
    if len(rows)!=count or len({r['path'] for r in rows})!=count:raise ValueError('Incomplete RP1-ID backup chain')
    return rows


def accepted_pair(directory,profile):
    if profile not in (TRIAL,RESTORE):raise ValueError('Explicit pair profile required')
    report=package.inspect(directory)
    zsh=base.socket_package.inspect(base.SOCKET)
    if zsh['image_sha256']!=prior.core.GOOD_SHA or sha(OLD_FIRMWARE)!=OLD_FW_SHA:raise ValueError('Original recovery pair changed')
    original={'bl31.bin':(OLD_FIRMWARE,OLD_FW_SHA),'probe.bin':(Path(zsh['image']),prior.core.GOOD_SHA)}
    candidate={'bl31.bin':(Path(report['firmware']),report['firmware_sha256']),
        'probe.bin':(Path(report['image']),report['image_sha256'])}
    old,new=(original,candidate) if profile==TRIAL else (candidate,original)
    files=[dict(target=name,candidate='candidate-'+name,old_sha256=old[name][1],new_sha256=new[name][1],
        old_bytes=old[name][0].stat().st_size,new_bytes=new[name][0].stat().st_size) for name in core.TARGETS]
    return files,{name:str(new[name][0]) for name in core.TARGETS},report,zsh


def load_plan(boot,baseline,directory,restore=False):
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux boot UUID required')
    baseline=baseline.resolve();directory=directory.resolve()
    if baseline.parent!=ROOT/'build/rpi5':raise ValueError('Exact local preceding transition required')
    plan=json.loads((baseline/'plan.json').read_text());result=json.loads((baseline/'result.json').read_text())
    profile=RESTORE if restore else TRIAL
    if not restore:
        prior.validate_result(result,plan)
        if plan['profile']!='root96-restore-v1':raise ValueError('Restored root96 normal firmware/zsh baseline required')
        rows=prior.inherited(plan,result,82)
    else:
        validate_result(result,plan)
        if plan['profile']!=TRIAL or boot==plan['linux_boot_id'] or plan['package']!=str(directory):
            raise ValueError('Exact installed pair and distinct Linux return required')
        rows=inherited(plan,result,87)
    for name,pin in plan['source_sha256'].items():
        if sha(baseline/'source-snapshots'/Path(name).name)!=pin:raise ValueError('Archived preceding source drift')
    files,candidates,report,zsh=accepted_pair(directory,profile)
    binding=copy.deepcopy(plan['identity_binding'])
    if boot!=result['identity']['boot_id']:binding['linux_boot_id_before_write']=result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot
    if binding['linux_boot_id_before_write']==boot:raise ValueError('Distinct Linux boot witness absent')
    protected=dict(result['protected_files_sha256'])
    for row in files:
        if protected.pop(row['target'])!=row['old_sha256']:raise ValueError('Previous exact installed pair differs')
    result=dict(host=HOST,profile=profile,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
        package=str(directory),preflight=report,working_zsh_preflight=zsh,nvme_backups=rows,
        protected_sha256={k:r['sha256'] for k,r in result['protected_after'].items()},protected_files=protected,
        ancestry=dict(directory=str(baseline),hashes={n:sha(baseline/n) for n in ('plan.json','result.json')}),
        source_sha256=source_pins(),no_hfs_mount=True,no_config_change=True,no_reboot=True,
        explicit_firmware_change=True,power_loss_atomicity_claimed=False,
        backup_policy='retained-good-sd-plus-complete-raw-and-file-ssd-v1')
    core.validate_files(result)
    return result


def validate_result(result,plan):
    core.validate_files(plan)
    exact=load_plan(plan['linux_boot_id'],Path(plan['ancestry']['directory']),Path(plan['package']),plan['profile']==RESTORE)
    if not base.reference.same({k:v for k,v in plan.items() if k!='run'},exact):raise ValueError('Exact pair plan provenance differs')
    expected=dict(plan['protected_files']);preserved={}
    for row in plan['files']:
        backup,_,nvme=core.NAMES[plan['profile']][row['target']]
        expected[row['target']]=row['new_sha256']
        if backup is not None:expected[backup]=row['old_sha256']
        preserved[row['target']]=dict(sha256=row['old_sha256'],bytes=row['old_bytes'],sd_backup=backup,nvme_backup=nvme)
    required=dict(status='installed',run=plan['run'],pair_publication_order=list(core.TARGETS),
        reused_existing_sd_backups={core.REUSED_ZSH_BACKUP:prior.core.GOOD_SHA} if plan['profile']==TRIAL else {},
        pair_sha256={r['target']:r['new_sha256'] for r in plan['files']},preserved_pair=preserved,
        nvme_previous_pair_sha256={r['target']:r['old_sha256'] for r in plan['files']},
        protected_files_sha256=expected,nvme_backups_verified=plan['nvme_backups'],
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
        temporary_pair_published=True,power_loss_atomicity_claimed=False,no_implicit_rollback=True,
        boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,firmware_changed=True,
        backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
            for key,node,_,length,name in base.core.EXTENTS])
    if any(not base.reference.same(result.get(k),v) for k,v in required.items()):raise ValueError('Incomplete typed RP1-ID pair receipt')
    if set(result.get('protected_after',{}))!={'mbr','boot','hfs'}:raise ValueError('Post-publication extents incomplete')
    for key,node,_,length,_ in base.core.EXTENTS:
        row=result['protected_after'][key]
        if row.get('device')!=node or type(row.get('bytes')) is not int or row['bytes']!=length or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):
            raise ValueError('Post-publication extent shape differs')
        if key!='boot' and row['sha256']!=plan['protected_sha256'][key]:raise ValueError('Protected MBR/HFS changed')


def remote_source(plan):
    if source_pins()!=plan['source_sha256']:raise ValueError('Pair source changed')
    core.validate_files(plan);source='import types,json\n'
    for name,module in zip(('capture','helper','snapshots','reference','guarded','pair'),(*base.MODULES,core)):
        source+=f'{name}=types.ModuleType({name!r})\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(pair.execute(PLAN,capture,helper,snapshots,reference,guarded)))\n'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True);p.add_argument('--linux-boot-id',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--restore',action='store_true');p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    with lease.hold(ROOT,'rp1-id-pair-stage'):
        out=args.output.resolve()
        if out.parent!=ROOT/'build/rpi5':raise ValueError('Fresh local output required')
        plan=load_plan(args.linux_boot_id,args.baseline,args.package,args.restore);out.mkdir(exist_ok=False)
        archive=out/'source-snapshots';archive.mkdir()
        for name,pin in plan['source_sha256'].items():
            target=archive/Path(name).name;shutil.copyfile(name,target)
            if sha(target)!=pin:raise ValueError('Source archive drift')
        def save():(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        save()
        if not args.execute:print('LOCAL_RP1_ID_PLAN '+str(out));return 0
        if load_plan(args.linux_boot_id,args.baseline,args.package,args.restore)!=plan:raise ValueError('Inputs changed before SSH')
        prepare=base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-rp1-id-'")
        r=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
        work=json.loads(r.stdout)['run']
        if not re.fullmatch('/home/sandrzej/xnu-rp1-id-[a-z0-9_]{8}',work):raise ValueError('Unexpected SSD work directory')
        plan['run']=work;save()
        for row in plan['files']:
            subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                plan['candidates'][row['target']],HOST+':'+work+'/'+row['candidate']],check=True,timeout=60)
        source=remote_source(plan);(out/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
        try:r=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
        except subprocess.TimeoutExpired as error:
            for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
                (out/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
            (out/'outcome-unknown.txt').write_text('Inspect SSD journal and exact pair. No retry/reboot/implicit restoration.\n');raise
        (out/'remote.stdout').write_text(r.stdout);(out/'remote.stderr').write_text(r.stderr);r.check_returncode()
        result=json.loads(r.stdout);validate_result(result,plan)
        if source_pins()!=plan['source_sha256']:raise ValueError('Pair source changed during publication')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out);return 0


if __name__=='__main__':raise SystemExit(main())
