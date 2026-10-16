#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit corrected AXI trace pair after the actual root41 normal-pair restore."""
import copy
import json
from pathlib import Path
import re
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_trace_trial as original
import stage_root41_trial as prior
import pcie_axi_pair_core as core
import check_pcie_axi_trace_package as package

ROOT,HOST,SSH,sha,base=prior.ROOT,prior.HOST,prior.SSH,prior.sha,prior.base
OLD_FIRMWARE,OLD_FW_SHA=original.OLD_FIRMWARE,original.OLD_FW_SHA
TRIAL,RESTORE=core.TRIAL,core.RESTORE


def source_pins():
    modules=(sys.modules[__name__],original,prior,core,core.original,package,package.source,
        original.lease,*base.MODULES)
    paths=[Path(m.__file__).resolve() for m in modules]
    paths.extend(ROOT/'tools/rpi5'/name for name in (
        'pcie_axi_serial_core.py','serial_pcie_axi_trial.py','pcie_axi_evidence.py',
        'capture_pcie_axi_linux_return.py','capture_pcie_axi_failed_return.py','arm_pcie_axi_reboot.py',
        'tests/test_pcie_axi_trial.py','tests/test_pcie_axi_trace_package.py',
        'pcie_trace_serial_core.py','serial_pcie_trace_trial.py','pcie_trace_evidence.py',
        'capture_pcie_trace_linux_return.py','capture_pcie_trace_failed_return.py','arm_pcie_trace_reboot.py',
        'tests/test_arm_pcie_trace_reboot.py','build_pcie_id_trace_package.py','pcie_id_serial_core.py'))
    return {str(p):sha(p) for p in paths}


def load_plan(boot,baseline,directory,restore=False):
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux boot UUID required')
    baseline=baseline.resolve();directory=directory.resolve()
    if baseline.parent!=ROOT/'build/rpi5':raise ValueError('Exact local preceding transition required')
    plan=json.loads((baseline/'plan.json').read_text());result=json.loads((baseline/'result.json').read_text())
    profile=RESTORE if restore else TRIAL
    if not restore:
        prior.validate_result(result,plan)
        if plan['profile']!=prior.MODES['restore']:raise ValueError('Actual restored root41 normal firmware/zsh baseline required')
        rows=prior.inherited(plan,result,118)
    else:
        validate_result(result,plan)
        if plan['profile']!=TRIAL or boot==plan['linux_boot_id'] or plan['package']!=str(directory):
            raise ValueError('Exact installed corrected pair and distinct Linux return required')
        rows=inherited(plan,result,123)
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
    output=dict(host=HOST,profile=profile,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
        package=str(directory),preflight=report,working_zsh_preflight=zsh,nvme_backups=rows,
        protected_sha256={k:r['sha256'] for k,r in result['protected_after'].items()},protected_files=protected,
        ancestry=dict(directory=str(baseline),hashes={n:sha(baseline/n) for n in ('plan.json','result.json')}),
        source_sha256=source_pins(),no_hfs_mount=True,no_config_change=True,no_reboot=True,
        explicit_firmware_change=True,power_loss_atomicity_claimed=False,
        backup_policy='retained-good-sd-plus-complete-raw-and-file-ssd-v1')
    core.validate_files(output)
    return output


def remote_source(plan):
    if source_pins()!=plan['source_sha256']:raise ValueError('Corrected AXI pair source changed')
    core.validate_files(plan);source='import types,json,sys\n'
    for name,module in zip(('capture','helper','snapshots','reference','guarded','pcie_trace_pair_core','pair'),
                           (*base.MODULES,core.original,core)):
        source+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(pair.execute(PLAN,capture,helper,snapshots,reference,guarded)))\n'


_bindings=dict(original.__dict__,prior=prior,core=core,package=package,TRIAL=TRIAL,RESTORE=RESTORE,
    source_pins=source_pins,load_plan=load_plan,remote_source=remote_source,__file__=__file__,__doc__=__doc__)
for _name in ('inherited','accepted_pair','validate_result','main'):
    _fn=getattr(original,_name)
    _bindings[_name]=types.FunctionType(_fn.__code__,_bindings,_name,_fn.__defaults__,_fn.__closure__)
    globals()[_name]=_bindings[_name]


if __name__=='__main__':raise SystemExit(main())
