#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed bounded C22 read trial; exact config/loader restoration intake.

Only temporary management enable/divider and exact read commands are permitted
by the separately checked package. No PHY writes, packet/DMA/IRQ activation.
The immutable publisher and modem-gated receive-only body remain unchanged.
"""
import builtins
import json
from pathlib import Path
import subprocess
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gem_capabilities_trial_v1 as previous
import stage_display_allocate_zero_trial as observer
prior=previous.prior
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_gem_mdio_package','tools.rpi5.pcie_gem_mdio_serial_core',
    'RPI5XNU:BL33:PCIE_GEM_MDIO_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-gem-mdio':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)
sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph


def source_pins():
    names=('gem_mdio_trial_v1.py','serial_gem_mdio_trial_v1.py','gem_mdio_evidence_v1.py',
        'tests/test_gem_mdio_trial_v1.py')
    return previous.source_pins()|observer.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def baseline(directory,seal_sha,plan_sha):
    context=observer.restoration(directory,seal_sha,plan_sha)
    files=context['result']['publication']['protected_files_sha256']
    if files.get('config.txt')!=observer.engine.ORIGINAL_CONFIG_SHA or any(files.get(n)!=v[1] for n,v in GOOD.items()):
        raise ValueError('Exact zero-allocation original config/firmware/zsh restoration required')
    return context


def completed_restore(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    if (context['plan']['media'].get('controller')!='reviewed-case-active-window-v3' or
        context['result']['publication']['pair_sha256']!={n:v[1] for n,v in GOOD.items()}):
        raise ValueError('Exact completed MDIO pair restoration required')
    selected=load_descriptor(context['plan']['media']['descriptor'])
    valid_report(context['plan']['media']['preflight'],selected)
    return context


def load_descriptor(reference):
    import serial_gem_mdio_trial_v1
    import gem_mdio_evidence_v1
    selected=get_descriptor(reference);protocol=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(protocol,n) for n in names) or protocol.PREPARED_PREFIX!=protocol.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact MDIO capture/replay API required')
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
    import serial_gem_mdio_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];selected=load_descriptor(media['descriptor']);report=media['preflight']
    valid_report(report,selected)
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_gem_mdio_trial_v1.py' or
        bound.__globals__['protocol'] is not selected['protocol'] or
        bound.__globals__['assert_modem_ready'] is not recorder.assert_modem_ready):
        raise ValueError('Exact new MDIO receiver and modem gate required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,modem_gate_bound_before_arm=True,hardware_executed=False)


def valid_report(report,selected):
    record=selected['record'];source=selected['protocol'].package_source
    if (record['package']!=str(ROOT/'build/rpi5/pcie-id-trial-qthzh5e7') or
        record['package_manifest_sha256']!='6c18b4c7b24346fdd08cda0f8e187d502b694e5f8d0bb8f79973641d24a44173' or
        report.get('manifest_sha256')!=record['package_manifest_sha256'] or
        report.get('image_sha256')!='181e58ee6326b625b3c58a1d2c288d16db0e0c1498fdf4f9ed8bb965e7436026' or
        type(report.get('image_bytes')) is not int or report.get('image_bytes')!=18193720 or report.get('image')!=str(ROOT/'build/rpi5/pcie-id-trial-qthzh5e7/probe.bin') or
        report.get('marker')!=record['marker'] or
        report.get('marker')!='RPI5XNU:BL33:PCIE_GEM_MDIO_TRIAL TAG=bff69a28a78d4f3087da5f4ac6ec8b22 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        report.get('firmware_sha256')!=record['firmware_sha256'] or
        any(not engine.same(report.get(name),getattr(source,name)()) for name in
            ('mdio_contract','capabilities_contract','selected_clock_contract','root_forward_contract','gem_contract',
             'decode_contract','assignment_contract','trace_contract')) or
        not engine.same(report.get('bars_contract'),json.loads((source.PRIOR_PACKAGE/'manifest.json').read_text())['bars_contract']) or
        not engine.same(report.get('owner_trace'),source.owner_contract()) or
        not engine.same(report.get('guard_composition'),source.guard_contract()) or
        report.get('endpoint_register_writes') is not True or report.get('phy_register_writes') is not False or report.get('endpoint_register_access') is not True or
        report.get('root_config_memory_writes') is not True or report.get('root_command_changes_mem_only') is not True or
        report.get('selected_source_profile_not_independent_clock_measurement') is not True):
        raise ValueError('Exact audited immutable GEM MDIO package report required')
    return True


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot)
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('gem_mdio_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_gem_mdio_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=completed_restore,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)
if __name__=='__main__':main()
