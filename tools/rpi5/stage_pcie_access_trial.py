#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct read-only PCIe candidate/restore profiles on the restored baseline.

Plan by default. Reuse the immutable guarded publisher in an isolated remote
namespace; never change its historical profile map or accepted validators.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_watchdog_recovery_trial as base
import check_watchdog_recovery_evidence as recovery
import check_pcie_access_package as package

ROOT, HOST, SSH = base.ROOT, base.HOST, base.SSH
PACKAGE = ROOT/'build/rpi5/pcie-access-vo0exx93'
IMAGE_SHA = 'f276e0be0d6c9d670189f425c623a86de70e5defce413315d03ab458dd02b10d'
MANIFEST_SHA = 'e28aed3208f013a05872907cfa202695822d5ac1cdf06e132668261457012c45'
NAMES = {
    'pcie-access-trial': ('probe.socket-identity-pre-pcie-access-20261012.bin',
        'probe.pcie-access-20261012.tmp', 'socket-identity-pre-pcie-access.bin'),
    'pcie-access-restore': ('probe.pcie-access-trial-20261012.bin',
        'probe.socket-identity-post-pcie-access-20261012.tmp', 'pcie-access-trial.bin'),
}
sha = base.sha


def source_pins():
    paths = (Path(__file__), Path(base.__file__), Path(package.__file__), Path(recovery.__file__),
        *(Path(m.__file__) for m in base.MODULES), ROOT/'tools/rpi5/tests/test_pcie_access_install.py')
    return {str(p):sha(p) for p in paths}


def validate_result(result, plan):
    if plan['profile'] not in NAMES: raise ValueError('Exact PCIe access profile required')
    expected = (base.prior.NEW_SHA, IMAGE_SHA) if plan['profile']=='pcie-access-trial' else (IMAGE_SHA,base.prior.NEW_SHA)
    if (plan['old_image_sha256'],plan['new_image_sha256']) != expected: raise ValueError('Wrong fixed image transition')
    # Reuse the actual typed receipt validator with a PRIVATE map view. Its
    # globals and the shared publisher's historical profile map stay unchanged.
    namespace = dict(base.validate_result.__globals__)
    namespace['core'] = types.SimpleNamespace(NAMES=NAMES, EXTENTS=base.core.EXTENTS)
    types.FunctionType(base.validate_result.__code__, namespace)(result, plan)


def load_plan(boot_id, restore_from=None):
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot_id): raise ValueError('SSD boot UUID required')
    recovery_report = recovery.inspect()
    report = package.inspect(PACKAGE)
    if report['image_sha256'] != IMAGE_SHA or report['manifest_sha256'] != MANIFEST_SHA: raise ValueError('Exact access candidate required')
    if not recovery_report['recovery_trial_pass']: raise ValueError('Physical recovery prerequisite absent')
    if restore_from is None:
        directory = recovery.RESTORE
        plan=json.loads((directory/'plan.json').read_text()); result=json.loads((directory/'result.json').read_text())
        base.validate_result(result,plan)
        rows=base.inherited(plan,result,38592,base.core.NAMES['watchdog-only-restore'][2],52)
        candidate, preflight, profile = report['image'],report,'pcie-access-trial'
        old_hash,new_hash = base.prior.NEW_SHA,IMAGE_SHA
    else:
        directory=restore_from.resolve()
        if directory.parent != ROOT/'build/rpi5': raise ValueError('Local installation receipt required')
        plan=json.loads((directory/'plan.json').read_text()); result=json.loads((directory/'result.json').read_text())
        validate_result(result,plan)
        if plan['profile']!='pcie-access-trial' or boot_id==plan['linux_boot_id']:
            raise ValueError('Distinct SSD return from exact access trial required')
        rows=base.inherited(plan,result,19384000,NAMES['pcie-access-trial'][2],56)
        preflight=base.socket_package.inspect(base.SOCKET)
        if preflight['image_sha256']!=base.prior.NEW_SHA: raise ValueError('Working zsh image changed')
        candidate,profile=preflight['image'],'pcie-access-restore'
        old_hash,new_hash=IMAGE_SHA,base.prior.NEW_SHA
    binding=copy.deepcopy(plan['identity_binding'])
    # Restoration and the next staging can legitimately share one verified
    # Linux boot. Preserve the earlier distinct-boot witness in that case;
    # don't require a gratuitous reboot just to reuse the identity helper.
    if boot_id!=result['identity']['boot_id']: binding['linux_boot_id_before_write']=result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot_id
    if binding['linux_boot_id_before_write']==boot_id: raise ValueError('No distinct SSD return witness')
    protected=dict(result['protected_files_sha256']); del protected['probe.bin']
    return dict(host=HOST,profile=profile,candidate=candidate,old_image_sha256=old_hash,new_image_sha256=new_hash,
        linux_boot_id=boot_id,identity_binding=binding,nvme_backups=rows,
        protected_sha256={k:r['sha256'] for k,r in result['protected_after'].items()},protected_files=protected,
        preflight=preflight,recovery_prerequisite=recovery_report,
        ancestry=dict(directory=str(directory),hashes={n:sha(directory/n) for n in ('plan.json','result.json')}),
        source_sha256=source_pins(),no_hfs_mount=True,no_config_change=True,no_pcie_access=True,no_reboot=True)


def remote_source(plan):
    if source_pins()!=plan['source_sha256'] or plan['profile'] not in NAMES: raise ValueError('Source/profile changed')
    source='import types,json\n'
    for name,module in zip(('capture','helper','snapshots','reference','trial'),base.MODULES):
        source+=f'{name}=types.ModuleType({name!r})\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    source+='trial.NAMES.update('+repr(NAMES)+')\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(trial.execute(PLAN,capture,helper,snapshots,reference)))\n'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linux-boot-id',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--restore-from',type=Path);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv);out=args.output.resolve()
    if out.parent!=ROOT/'build/rpi5': raise ValueError('Fresh local evidence child required')
    plan=load_plan(args.linux_boot_id,args.restore_from);out.mkdir(exist_ok=False)
    archived=out/'source-snapshots';archived.mkdir()
    for name,pin in plan['source_sha256'].items():
        target=archived/Path(name).name;shutil.copyfile(name,target)
        if sha(target)!=pin: raise ValueError('Source snapshot drift')
    def save(): (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    save()
    if not args.execute: print('LOCAL_PLAN_ONLY '+str(out));return 0
    if load_plan(args.linux_boot_id,args.restore_from)!=plan: raise ValueError('Inputs changed before SSH')
    prepare=base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-gate5-pcie-access-'")
    response=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
    work=json.loads(response.stdout)['run']
    if not re.fullmatch('/home/sandrzej/xnu-gate5-pcie-access-[a-z0-9_]{8}',work): raise ValueError('Unexpected SSD run')
    plan['run']=work;save()
    subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
        plan['candidate'],HOST+':'+work+'/candidate.bin'],check=True,timeout=60)
    source=remote_source(plan);(out/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try: response=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (out/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (out/'outcome-unknown.txt').write_text('Inspect same run and mount; no retry, reboot or blind restoration.\n');raise
    (out/'remote.stdout').write_text(response.stdout);(out/'remote.stderr').write_text(response.stderr)
    response.check_returncode();result=json.loads(response.stdout);validate_result(result,plan)
    if source_pins()!=plan['source_sha256']: raise ValueError('Source changed during installation')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out);return 0


if __name__=='__main__':raise SystemExit(main())
