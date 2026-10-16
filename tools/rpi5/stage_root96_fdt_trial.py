#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Corrected retained-FDT root96 install/restore after the exact ID pair return."""
import copy
import json
from pathlib import Path
import re
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_root96_trial as original
import stage_pcie_id_trial as preceding
import root96_fdt_media_core as core
import check_root96_fdt_package as package

ROOT,HOST,SSH,sha,base=original.ROOT,original.HOST,original.SSH,original.sha,original.base
MODES=dict(zip(('install','restore'),core.MODES))


def source_pins():
    modules=(sys.modules[__name__],original,preceding,core,core.original,package,package.builder,
             original.lease,*base.MODULES)
    paths=[Path(m.__file__).resolve() for m in modules]
    paths.extend(ROOT/'tools/rpi5'/name for name in (
        'root96_fdt_trial_core.py','serial_root96_fdt_trial.py','audit_root96_fdt_trial.py',
        'capture_root96_fdt_failed_return.py','tests/test_root96_fdt_trial.py','tests/test_root96_fdt_package.py',
        'root96_trial_core.py','serial_root96_trial.py','audit_root96_trial.py','capture_root96_failed_return.py',
        'audit_socket_identity_trial.py','capture_pcie_fw_reuse_linux_return.py'))
    return {str(p):sha(p) for p in paths}


inherited=original.inherited


def load_plan(operation,boot,baseline,candidate_package=None):
    if operation not in MODES or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):
        raise ValueError('Explicit corrected operation and fresh SSD Linux UUID required')
    baseline=baseline.resolve()
    if baseline.parent!=ROOT/'build/rpi5':raise ValueError('Exact local preceding receipt required')
    previous=json.loads((baseline/'plan.json').read_text());result=json.loads((baseline/'result.json').read_text())
    if operation=='install':
        preceding.validate_result(result,previous)
        if previous['profile']!=preceding.RESTORE:raise ValueError('Completed exact ID firmware/loader pair restore required')
        rows=preceding.inherited(previous,result,92)
        if candidate_package is None:raise ValueError('Exact corrected package required')
        preflight=package.inspect(candidate_package);candidate=preflight['image']
        oldhash,oldbytes=core.GOOD_SHA,core.GOOD_BYTES
        newhash,newbytes=preflight['image_sha256'],preflight['image_bytes']
    else:
        validate_result(result,previous)
        if previous['profile']!=MODES['install'] or boot==previous['linux_boot_id']:
            raise ValueError('Exact corrected installation and distinct Linux return required')
        rows=inherited(previous,result,96)
        preflight=base.socket_package.inspect(base.SOCKET);candidate=preflight['image']
        oldhash,oldbytes=previous['new_sha256'],previous['new_bytes']
        newhash,newbytes=core.GOOD_SHA,core.GOOD_BYTES
        if candidate_package is not None:raise ValueError('Restoration uses only the pinned known-good package')
    for name,pin in previous['source_sha256'].items():
        if sha(baseline/'source-snapshots'/Path(name).name)!=pin:raise ValueError('Archived preceding source differs')
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
    core.validate(plan);return plan


def remote_source(plan):
    if source_pins()!=plan['source_sha256']:raise ValueError('Corrected media source drift')
    core.validate(plan);source='import types,json,sys\n'
    for name,module in zip(('capture','helper','snapshots','reference','guarded','root96_media_core','media'),
                           (*base.MODULES,core.original,core)):
        source+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(media.execute(PLAN,capture,helper,snapshots,reference,guarded)))\n'


# Frozen generic receipt/publication functions run against a private namespace.
# Their original modules, source bytes, profiles, and accepted receipts stay intact.
_bindings=dict(original.__dict__,core=core,package=package,MODES=MODES,load_plan=load_plan,
               source_pins=source_pins,remote_source=remote_source,__doc__=__doc__)
validate_result=types.FunctionType(original.validate_result.__code__,_bindings)
_bindings['validate_result']=validate_result
main=types.FunctionType(original.main.__code__,_bindings,argdefs=original.main.__defaults__)


if __name__=='__main__':raise SystemExit(main())
