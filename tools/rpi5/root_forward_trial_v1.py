#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed root MEM/window trial with typed framebuffer-observer restoration.

The immutable pair publisher, one-shot reboot, zero-TX recorder and independent
return bodies are privately rebound, not replaced. No operation is implicit.
"""
import builtins
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gem_identify_trial_v1 as prior
import stage_framebuffer_observation_trial_v2 as observer
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_root_forward_package','tools.rpi5.pcie_root_forward_serial_core',
    'RPI5XNU:BL33:PCIE_ROOT_FORWARD_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-root-forward':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)


def source_pins():
    names=('root_forward_trial_v1.py','serial_root_forward_trial_v1.py','root_forward_evidence_v1.py',
        'tests/test_root_forward_trial_v1.py')
    return prior.source_pins()|observer.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def baseline(directory,seal_sha,plan_sha):
    directory=local(directory);plan=json.loads((directory/'plan.json').read_text());media=plan.get('media',{})
    # This untrusted discriminator selects only a fixed validator. That reader
    # verifies the independently retained seal, exact operation and originals.
    if media.get('controller')==observer.CONTROLLER and media.get('profile')==observer.engine.RESTORE:
        context=observer.restoration(directory,seal_sha,plan_sha)
        files=context['result']['publication']['protected_files_sha256']
        if any(files[n]!=v[1] for n,v in GOOD.items()):raise ValueError('Observer original pair not restored')
        return context
    return prior.baseline(directory,seal_sha,plan_sha)


def load_descriptor(reference):
    import serial_root_forward_trial_v1
    import root_forward_evidence_v1
    selected=get_descriptor(reference);protocol=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(protocol,n) for n in names) or protocol.PREPARED_PREFIX!=protocol.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact root-forward capture/replay API required')
    return selected


sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph
_prepare_install=private(prior._prepare_install,baseline=baseline,load_descriptor=load_descriptor,source_pins=source_pins)
load_installation=private(prior.load_installation,load_descriptor=load_descriptor,source_pins=source_pins)
dispatch=private(prior.dispatch,descriptors=descriptors)


def admit(checkpoint):
    import serial_root_forward_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];selected=load_descriptor(media['descriptor']);report=media['preflight']
    if report['marker']!=selected['record']['marker'] or report['firmware_sha256']!=selected['record']['firmware_sha256']:
        raise ValueError('Exact audited root-forward package report required')
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_root_forward_trial_v1.py' or
        bound.__globals__['protocol'] is not selected['protocol']):
        raise ValueError('Exact new root-forward recorder execution namespace required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot)
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('root_forward_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_root_forward_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=baseline,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)
if __name__=='__main__':main()
