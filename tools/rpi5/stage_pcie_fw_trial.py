#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Plan by default: exact-card dual firmware/BL33 install or explicit restore."""
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
import stage_pcie_access_trial as previous
import check_pcie_access_evidence as recovery
import check_pcie_fw_trial_package as package
import firmware_pair_install_core as core
import rpi5_board_lease as lease

base=previous.base
ROOT,HOST,SSH=previous.ROOT,previous.HOST,previous.SSH
PACKAGE=ROOT/'build/rpi5/pcie-fwabi-y_995zop'
IMAGE_SHA='3cd15bad801917b12352122cbf226f502cad043737730cf5e2bccc51636d9de6'
MANIFEST_SHA='c37e42b3925fb58ec4474511ec34accaccd8779c83682b170a076be30025c69a'
OLD_FIRMWARE=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
OLD_FW_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
sha=base.sha
MODULES=(*base.MODULES,core)


def source_pins():
    paths=(Path(__file__),Path(core.__file__),Path(previous.__file__),Path(recovery.__file__),
        Path(package.__file__),Path(package.builder.__file__),Path(base.__file__),
        *(Path(m.__file__) for m in base.MODULES),
        Path(lease.__file__),ROOT/'tools/rpi5/tests/test_pcie_fw_install.py',
        ROOT/'tools/rpi5/serial_pcie_fw_trial.py',ROOT/'tools/rpi5/tests/test_pcie_fw_recorder.py')
    return {str(p):sha(p) for p in paths}


def inherited_pair(plan,result,expected_count):
    rows=copy.deepcopy(plan['nvme_backups'])
    rows.extend(dict(path=result['run']+'/'+r['saved_as'],bytes=r['bytes'],sha256=r['sha256']) for r in result['backups'])
    for row in plan['files']:
        rows.append(dict(path=result['run']+'/'+core.NAMES[plan['profile']][row['target']][2],
            bytes=row['old_bytes'],sha256=row['old_sha256']))
    if len(rows)!=expected_count or len({r['path'] for r in rows})!=expected_count:raise ValueError('Incomplete/duplicate pair backup chain')
    return rows


def accepted_pair(profile):
    if profile not in core.NAMES:raise ValueError('Wrong exact pair profile')
    report=package.inspect(PACKAGE)
    if report['image_sha256']!=IMAGE_SHA or report['manifest_sha256']!=MANIFEST_SHA:
        raise ValueError('Accepted firmware ABI package changed')
    zsh=base.socket_package.inspect(base.SOCKET)
    if zsh['image_sha256']!=base.prior.NEW_SHA or sha(OLD_FIRMWARE)!=OLD_FW_SHA:raise ValueError('Known-good firmware/zsh changed')
    original={'bl31.bin':(OLD_FIRMWARE,OLD_FW_SHA),'probe.bin':(Path(zsh['image']),zsh['image_sha256'])}
    trial={'bl31.bin':(package.builder.FIRMWARE_BIN,report['firmware_sha256']),'probe.bin':(Path(report['image']),IMAGE_SHA)}
    old,new=(original,trial) if profile=='firmware-abi-trial' else (trial,original)
    files=[dict(target=n,candidate='candidate-'+n,old_sha256=old[n][1],new_sha256=new[n][1],
        old_bytes=old[n][0].stat().st_size,new_bytes=new[n][0].stat().st_size) for n in core.TARGETS]
    return files,{n:str(new[n][0]) for n in core.TARGETS},report,zsh


def load_plan(boot_id,restore_from=None):
    if not isinstance(boot_id,str) or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot_id):
        raise ValueError('Fresh SSD boot UUID required')
    witness=recovery.inspect()
    if not witness['read_only_access_trial_pass'] or not witness['autonomous_recovery_observed']:
        raise ValueError('Prior physical access/reset-return prerequisite absent')
    profile='firmware-abi-trial' if restore_from is None else 'firmware-abi-restore'
    files,candidates,report,zsh=accepted_pair(profile)
    if restore_from is None:
        directory=recovery.RESTORE
        prior_plan=json.loads((directory/'plan.json').read_text());prior_result=json.loads((directory/'result.json').read_text())
        previous.validate_result(prior_result,prior_plan)
        rows=base.inherited(prior_plan,prior_result,53376,previous.NAMES['pcie-access-restore'][2],60)
    else:
        directory=restore_from.resolve()
        if directory.parent!=ROOT/'build/rpi5':raise ValueError('Local installed pair receipt required')
        prior_plan=json.loads((directory/'plan.json').read_text());prior_result=json.loads((directory/'result.json').read_text())
        validate_result(prior_result,prior_plan)
        if prior_plan['profile']!='firmware-abi-trial' or boot_id==prior_plan['linux_boot_id']:
            raise ValueError('Distinct SSD Linux return from exact pair required')
        rows=inherited_pair(prior_plan,prior_result,65)
    binding=copy.deepcopy(prior_plan['identity_binding'])
    if boot_id!=prior_result['identity']['boot_id']:binding['linux_boot_id_before_write']=prior_result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot_id
    if binding['linux_boot_id_before_write']==boot_id:raise ValueError('No distinct intervening SSD boot witness')
    protected=dict(prior_result['protected_files_sha256'])
    for row in files:
        if protected.pop(row['target'])!=row['old_sha256']:raise ValueError('Prior installed pair differs')
    return dict(host=HOST,profile=profile,files=files,candidates=candidates,linux_boot_id=boot_id,identity_binding=binding,
        nvme_backups=rows,protected_sha256={k:r['sha256'] for k,r in prior_result['protected_after'].items()},
        protected_files=protected,preflight=report,working_zsh_preflight=zsh,recovery_prerequisite=witness,
        ancestry=dict(directory=str(directory),hashes={n:sha(directory/n) for n in ('plan.json','result.json')}),
        source_sha256=source_pins(),no_hfs_mount=True,no_config_change=True,no_reboot=True,
        explicit_firmware_change=True,power_loss_atomicity_claimed=False)


def validate_result(result,plan):
    core.validate_files(plan)
    restore=Path(plan['ancestry']['directory']) if plan['profile']=='firmware-abi-restore' else None
    exact=load_plan(plan['linux_boot_id'],restore)
    if not base.reference.same({k:v for k,v in plan.items() if k!='run'},exact):
        raise ValueError('Pair receipt plan differs from exact ancestry/baseline/backup chain')
    files,_,report,zsh=accepted_pair(plan['profile'])
    if plan['files']!=files or plan['preflight']!=report or plan['working_zsh_preflight']!=zsh:
        raise ValueError('Wrong pinned pair transition/preflight')
    expected=dict(plan['protected_files'])
    preserved={}
    for row in files:
        backup,_,nvme=core.NAMES[plan['profile']][row['target']]
        expected[row['target']]=row['new_sha256'];expected[backup]=row['old_sha256']
        preserved[row['target']]=dict(sha256=row['old_sha256'],bytes=row['old_bytes'],sd_backup=backup,nvme_backup=nvme)
    required=dict(status='installed',run=plan['run'],pair_publication_order=list(core.TARGETS),
        pair_sha256={r['target']:r['new_sha256'] for r in files},preserved_pair=preserved,
        nvme_previous_pair_sha256={r['target']:r['old_sha256'] for r in files},
        protected_files_sha256=expected,nvme_backups_verified=plan['nvme_backups'],
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
        temporary_pair_published=True,power_loss_atomicity_claimed=False,no_implicit_rollback=True,
        boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,firmware_changed=True,
        backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
            for key,node,_,length,name in base.core.EXTENTS])
    if any(not base.reference.same(result.get(k),v) for k,v in required.items()):raise ValueError('Incomplete/wrong typed pair receipt')
    if set(result.get('protected_after',{}))!={r[0] for r in base.core.EXTENTS}:raise ValueError('Incomplete post-pair extent set')
    for key,node,_,length,_ in base.core.EXTENTS:
        r=result['protected_after'][key]
        if r.get('device')!=node or type(r.get('bytes')) is not int or r['bytes']!=length or not re.fullmatch('[0-9a-f]{64}',r.get('sha256','')):
            raise ValueError('Incomplete post-pair raw extent')
        if key!='boot' and r['sha256']!=plan['protected_sha256'][key]:raise ValueError('Protected MBR/HFS changed')


def remote_source(plan):
    if source_pins()!=plan['source_sha256']:raise ValueError('Pair sources changed')
    core.validate_files(plan)
    source='import types,json\n'
    for name,module in zip(('capture','helper','snapshots','reference','guarded','pair'),MODULES):
        source+=f'{name}=types.ModuleType({name!r})\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(pair.execute(PLAN,capture,helper,snapshots,reference,guarded)))\n'


def _main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-boot-id',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--restore-from',type=Path);p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    out=args.output.resolve()
    if out.parent!=ROOT/'build/rpi5':raise ValueError('Fresh local evidence child required')
    plan=load_plan(args.linux_boot_id,args.restore_from);out.mkdir(exist_ok=False)
    archive=out/'source-snapshots';archive.mkdir()
    for name,pin in plan['source_sha256'].items():
        target=archive/Path(name).name;shutil.copyfile(name,target)
        if sha(target)!=pin:raise ValueError('Archived pair source drift')
    def save():(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    save()
    if not args.execute:print('LOCAL_PAIR_PLAN_ONLY '+str(out));return 0
    if load_plan(args.linux_boot_id,args.restore_from)!=plan:raise ValueError('Pair inputs changed before SSH')
    prepare=base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-gate5-fwabi-'")
    r=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
    work=json.loads(r.stdout)['run']
    if not re.fullmatch('/home/sandrzej/xnu-gate5-fwabi-[a-z0-9_]{8}',work):raise ValueError('Unexpected SSD pair run')
    plan['run']=work;save()
    for row in plan['files']:
        subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
            plan['candidates'][row['target']],HOST+':'+work+'/'+row['candidate']],check=True,timeout=60)
    source=remote_source(plan);(out/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:r=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (out/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (out/'outcome-unknown.txt').write_text('Inspect same SSD run, pair journal and mount state. No retry, reboot or blind restoration.\n');raise
    (out/'remote.stdout').write_text(r.stdout);(out/'remote.stderr').write_text(r.stderr)
    r.check_returncode();result=json.loads(r.stdout);validate_result(result,plan)
    if source_pins()!=plan['source_sha256']:raise ValueError('Pair source drift during installation')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out);return 0


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if '--execute' not in argv:return _main(argv)
    with lease.hold(ROOT,'firmware-pair-publication'):return _main(argv)


if __name__=='__main__':raise SystemExit(main())
