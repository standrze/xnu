#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed selected-SYS-profile successor; unchanged guarded pair publisher.

The prior completed pair restoration is byte-validated, not compiler-replayed.
The new receiver retains checked pre-ARM modem control and zero UART payload TX.
No operation is implicit and register-profile admission is not clock measurement.
"""
import builtins
from pathlib import Path
import subprocess
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_forward_trial_v2 as previous
prior=previous.prior
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_gem_selected_package','tools.rpi5.pcie_gem_selected_serial_core',
    'RPI5XNU:BL33:PCIE_GEM_SELECTED_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-gem-selected':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)
sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph


def source_pins():
    names=('gem_selected_trial_v1.py','serial_gem_selected_trial_v1.py','gem_selected_evidence_v1.py',
        'tests/test_gem_selected_trial_v1.py')
    return previous.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def baseline(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    if (context['plan']['media'].get('controller')!='reviewed-case-active-window-v3' or
        context['result']['publication']['pair_sha256']!={n:v[1] for n,v in GOOD.items()}):
        raise ValueError('Exact typed completed original firmware/zsh pair restoration required')
    return context


def load_descriptor(reference):
    import serial_gem_selected_trial_v1
    import gem_selected_evidence_v1
    selected=get_descriptor(reference);protocol=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(protocol,n) for n in names) or protocol.PREPARED_PREFIX!=protocol.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact selected-clock capture/replay API required')
    return selected


_prepare_install=private(prior._prepare_install,baseline=baseline,load_descriptor=load_descriptor,source_pins=source_pins)
load_installation=private(prior.load_installation,load_descriptor=load_descriptor,source_pins=source_pins)


def upload_run(command,**kwargs):
    """Only the original candidate SCP call gains compression and a 180s bound.

    SSH creation/publication arguments and timeouts are forwarded unchanged.
    A failed upload propagates before the original publisher intent/dispatch;
    this adapter performs no retry and never executes the SD program itself.
    """
    if command and command[0]=='scp':
        prefix=['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
        if not isinstance(command,list) or len(command)!=9 or command[:7]!=prefix or kwargs!={'check':True,'timeout':60}:
            raise ValueError('Exact original bounded candidate-upload call required')
        command=[command[0],'-C',*command[1:]]
        kwargs=dict(kwargs,timeout=180)
    return subprocess.run(command,**kwargs)


upload_transport=types.SimpleNamespace(run=upload_run)
dispatch=private(prior.dispatch,descriptors=descriptors,subprocess=upload_transport)


def admit(checkpoint):
    import serial_gem_selected_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];selected=load_descriptor(media['descriptor']);report=media['preflight']
    if (report['marker']!=selected['record']['marker'] or
        report['firmware_sha256']!=selected['record']['firmware_sha256'] or
        not engine.same(report.get('selected_clock_contract'),selected['protocol'].package_source.selected_clock_contract())):
        raise ValueError('Exact audited selected-clock package report required')
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_gem_selected_trial_v1.py' or
        bound.__globals__['protocol'] is not selected['protocol'] or
        bound.__globals__['assert_modem_ready'] is not recorder.assert_modem_ready):
        raise ValueError('Exact new selected-clock receiver and modem gate required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,modem_gate_bound_before_arm=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot)
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('gem_selected_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_gem_selected_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=baseline,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)
if __name__=='__main__':main()
