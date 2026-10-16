#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed contained BAR case, unchanged pair publisher, typed loader restoration intake."""
import builtins
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_trial_v3 as prior
import stage_root42_pthread_trial as loader

ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_rp1_bars_root_package','tools.rpi5.rp1_bars_root_serial_core',
    'RPI5XNU:BL33:RP1_BARS_ROOT_TRIAL TAG=',True)
get_descriptor=private(prior.descriptors.get,ADAPTERS={'rp1-contained-bars':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)


def source_pins():
    names=('bars_root_trial_v1.py','serial_bars_root_trial_v1.py','bars_root_evidence_v1.py',
        'tests/test_bars_root_trial_v1.py')
    return prior.source_pins()|loader.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def load_descriptor(reference):
    import serial_bars_root_trial_v1
    import bars_root_evidence_v1
    selected=get_descriptor(reference);p=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(p,n) for n in names) or p.PREPARED_PREFIX!=p.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact capture/replay protocol API required')
    return selected


def baseline(directory,seal_sha,plan_sha):
    # Reading this discriminator grants no authority. The selected typed engine
    # then verifies the complete retained seal, plan and publication result.
    directory=local(directory);plan=json.loads((directory/'plan.json').read_text())
    if plan.get('media',{}).get('profile')==loader.engine.RESTORE:
        context=loader.restoration(directory,seal_sha,plan_sha)
        files=context['result']['publication']['protected_files_sha256']
        if any(files[name]!=value[1] for name,value in GOOD.items()):
            raise ValueError('Original pair not restored by single-loader operation')
        return context
    return prior.baseline(directory,seal_sha,plan_sha)


sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph
prepare_install=private(prior.prepare_install,baseline=baseline,load_descriptor=load_descriptor,source_pins=source_pins)
load_installation=private(prior.load_installation,load_descriptor=load_descriptor,source_pins=source_pins)
dispatch=private(prior.dispatch,descriptors=descriptors)


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('bars_root_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_bars_root_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=baseline,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)


if __name__=='__main__':main()
