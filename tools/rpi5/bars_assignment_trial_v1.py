#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed BAR assignment/restoration trial over the immutable dual-pair publisher.

Accept the exact completed root45 loader restoration through its typed reader.
No publisher, hardware bounds, capture policy or retry behavior is changed.
"""
import builtins
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import owner_trace_trial_v1 as prior
import stage_root45_entropy_trial as ready
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_bars_assignment_package','tools.rpi5.pcie_bars_assignment_serial_core',
    'RPI5XNU:BL33:PCIE_BARS_ASSIGNMENT_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-bars-assignment':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)


def source_pins():
    names=('bars_assignment_trial_v1.py','serial_bars_assignment_trial_v1.py','bars_assignment_evidence_v1.py',
        'tests/test_bars_assignment_trial_v1.py')
    return prior.source_pins()|ready.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def load_descriptor(reference):
    import serial_bars_assignment_trial_v1
    import bars_assignment_evidence_v1
    selected=get_descriptor(reference);p=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(p,n) for n in names) or p.PREPARED_PREFIX!=p.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact BAR assignment capture/replay API required')
    return selected


def baseline(directory,seal_sha,plan_sha):
    directory=local(directory);plan=json.loads((directory/'plan.json').read_text());media=plan.get('media',{})
    # Only select a fixed typed validator here. The discriminator itself is
    # untrusted; restoration verifies the seal, original pair and full result.
    if media.get('profile')==ready.engine.RESTORE and media.get('controller')==ready.CONTROLLER:
        context=ready.restoration(directory,seal_sha,plan_sha)
        files=context['result']['publication']['protected_files_sha256']
        if any(files[n]!=v[1] for n,v in GOOD.items()):raise ValueError('Root45 original pair not restored')
        return context
    return prior.baseline(directory,seal_sha,plan_sha)


sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph
_prepare_install=private(prior.prepare_install,baseline=baseline,load_descriptor=load_descriptor,source_pins=source_pins)
load_installation=private(prior.load_installation,load_descriptor=load_descriptor,source_pins=source_pins)
dispatch=private(prior.dispatch,descriptors=descriptors)


def admit(checkpoint):
    import serial_bars_assignment_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];selected=load_descriptor(media['descriptor'])
    report=media['preflight']
    if report['marker']!=selected['record']['marker'] or report['firmware_sha256']!=selected['record']['firmware_sha256']:
        raise ValueError('Exact audited assignment package report required')
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_bars_assignment_trial_v1.py' or
        bound.__globals__['protocol'] is not selected['protocol']):
        raise ValueError('Exact new recorder execution namespace required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot)
    metrics['recorder_admission']=admit(checkpoint)
    return checkpoint,pin,metrics


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('bars_assignment_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_bars_assignment_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=baseline,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)


if __name__=='__main__':main()
