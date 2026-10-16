#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact passive owner case over unchanged pair publisher and typed ready-root intake."""
import builtins
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bars_root_trial_v1 as prior
import stage_root42_ready_trial as ready
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_owner_trace_package','tools.rpi5.pcie_owner_trace_serial_core',
    'RPI5XNU:BL33:PCIE_OWNER_TRACE_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-owner-trace':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)


def source_pins():
    names=('owner_trace_trial_v1.py','serial_owner_trace_trial_v1.py','owner_trace_evidence_v1.py',
        'tests/test_owner_trace_trial_v1.py')
    return prior.source_pins()|ready.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def load_descriptor(reference):
    import serial_owner_trace_trial_v1
    import owner_trace_evidence_v1
    selected=get_descriptor(reference);p=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(p,n) for n in names) or p.PREPARED_PREFIX!=p.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact owner capture/replay API required')
    return selected


def baseline(directory,seal_sha,plan_sha):
    directory=local(directory);plan=json.loads((directory/'plan.json').read_text());media=plan.get('media',{})
    # This discriminator is not evidence. The exact typed restoration reader
    # then checks retained seal, controller, plan, original files and receipt.
    if media.get('profile')==ready.engine.RESTORE and media.get('controller')==ready.CONTROLLER:
        context=ready.restoration(directory,seal_sha,plan_sha)
        files=context['result']['publication']['protected_files_sha256']
        if any(files[n]!=v[1] for n,v in GOOD.items()):raise ValueError('Ready-root original pair not restored')
        return context
    return prior.baseline(directory,seal_sha,plan_sha)


sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph
prepare_install=private(prior.prepare_install,baseline=baseline,load_descriptor=load_descriptor,source_pins=source_pins)
load_installation=private(prior.load_installation,load_descriptor=load_descriptor,source_pins=source_pins)
dispatch=private(prior.dispatch,descriptors=descriptors)


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('owner_trace_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_owner_trace_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=baseline,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)


if __name__=='__main__':main()
