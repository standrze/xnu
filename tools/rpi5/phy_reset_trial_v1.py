#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact GPIO32 reset and C22 observation trial, with immutable rollback.

Only the frozen59-row candidate is accepted. The original pair publisher,
zero-TX receiver and one-shot launcher remain unchanged except fixed bindings.
No packet, DMA, IRQ or PHY-register-write authority is granted here.
"""
import builtins
import json
from pathlib import Path
import subprocess
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import phy_gpio_trial_v1 as previous
import stage_display_compact_trial as compact
import stage_display_xnu_trial as display_xnu
prior=previous.prior
ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local','private'))
ADAPTER=('tools.rpi5.check_pcie_phy_reset_package','tools.rpi5.pcie_phy_reset_serial_core',
    'RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG=',True)
get_descriptor=private(prior.get_descriptor,ADAPTERS={'pcie-phy-reset':ADAPTER})
descriptors=types.SimpleNamespace(get=get_descriptor)
sealed_operation=prior.sealed_operation
merge_pins=prior.merge_pins
package_graph=prior.package_graph


def source_pins():
    names=('phy_reset_trial_v1.py','serial_phy_reset_trial_v1.py','phy_reset_evidence_v1.py',
        'tests/test_phy_reset_trial_v1.py')
    return previous.source_pins()|compact.source_pins()|display_xnu.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def baseline(directory,seal_sha,plan_sha):
    # This untrusted discriminator selects only an explicit typed RESTORE
    # validator. Unknown, older and in-progress controller/profile pairs fail.
    plan=json.loads((local(directory)/'plan.json').read_text())
    media=plan.get('media',{})
    key=(media.get('controller'),media.get('profile'))
    readers={
        (compact.CONTROLLER,compact.engine.RESTORE):compact.restoration,
        (display_xnu.CONTROLLER,display_xnu.engine.RESTORE):display_xnu.restoration}
    if key not in readers:
        raise ValueError('Exact completed compact or XNU-display restoration required; no older fallback')
    context=readers[key](directory,seal_sha,plan_sha)
    files=context['result']['publication']['protected_files_sha256']
    if files.get('config.txt')!=compact.engine.ORIGINAL_CONFIG_SHA or any(files.get(n)!=v[1] for n,v in GOOD.items()):
        raise ValueError('Exact original config/firmware/zsh restoration required')
    return context


def completed_restore(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    if (context['plan']['media'].get('controller')!='reviewed-case-active-window-v3' or
        context['result']['publication']['pair_sha256']!={n:v[1] for n,v in GOOD.items()}):
        raise ValueError('Exact completed GPIO pair restoration required')
    selected=load_descriptor(context['plan']['media']['descriptor'])
    valid_report(context['plan']['media']['preflight'],selected)
    return context


def load_descriptor(reference):
    import serial_phy_reset_trial_v1
    import phy_reset_evidence_v1
    selected=get_descriptor(reference);protocol=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if any(not hasattr(protocol,n) for n in names) or protocol.PREPARED_PREFIX!=protocol.PREFIX+b'PREPARED ':
        raise ValueError('Complete exact GPIO capture/replay API required')
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
    import serial_phy_reset_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];selected=load_descriptor(media['descriptor']);report=media['preflight']
    valid_report(report,selected)
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_phy_reset_trial_v1.py' or
        bound.__globals__['protocol'] is not selected['protocol'] or
        bound.__globals__['assert_modem_ready'] is not recorder.assert_modem_ready):
        raise ValueError('Exact new GPIO receiver and modem gate required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,modem_gate_bound_before_arm=True,hardware_executed=False)


def valid_report(report,selected):
    record=selected['record'];source=selected['protocol'].package_source
    if (record['package']!=str(ROOT/'build/rpi5/pcie-id-trial-q5lw58tf') or
        record['package_manifest_sha256']!='0c8b015a71ce65269e4b4d2373745f399673c95db2e5e59f86b72231f658c6fb' or
        report.get('manifest_sha256')!=record['package_manifest_sha256'] or
        report.get('image_sha256')!='6627559f8dc8e3a78329203300b85507403a5a32c2d4b21a473834dac44c892f' or
        type(report.get('image_bytes')) is not int or report.get('image_bytes')!=18214120 or report.get('image')!=str(ROOT/'build/rpi5/pcie-id-trial-q5lw58tf/probe.bin') or
        report.get('marker')!=record['marker'] or
        report.get('marker')!='RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG=617795334d2b4c95a4e7712c4ac20b65 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        report.get('firmware_sha256')!=record['firmware_sha256'] or
        report.get('firmware_sha256')!='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b' or
        any(not isinstance(report.get(name),dict) or not report[name] or
            any(value is not True for value in report[name].values()) for name in ('checks','reset_package_checks')) or
        any(not engine.same(report.get(name),getattr(source,name)()) for name in
            ('reset_contract','capabilities_contract','selected_clock_contract','root_forward_contract','gem_contract',
             'decode_contract','assignment_contract','trace_contract')) or
        not engine.same(report.get('bars_contract'),json.loads((source.PRIOR_PACKAGE/'manifest.json').read_text())['bars_contract']) or
        not engine.same(report.get('owner_trace'),source.owner_contract()) or
        not engine.same(report.get('rp1_device_handoff'),source.gpio_handoff_contract()) or
        not engine.same(report.get('guard_composition'),source.guard_contract()) or
        report.get('endpoint_register_writes') is not True or report.get('gpio_reset_writes') is not True or report.get('phy_register_writes') is not False or report.get('endpoint_register_access') is not True or
        report.get('root_config_memory_writes') is not True or report.get('root_command_changes_mem_only') is not True or
        report.get('selected_source_profile_not_independent_clock_measurement') is not True):
        raise ValueError('Exact audited immutable GPIO reset/C22 package report required')
    return True


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot)
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('phy_reset_evidence_v1',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_phy_reset_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
prepare_restore=private(prior.prepare_restore,load_installation=load_installation,__builtins__=scoped)
launch=private(prior.launch,load_installation=load_installation,__builtins__=scoped)
replay=private(prior.replay,baseline=completed_restore,load_installation=load_installation,prepare_restore=prepare_restore,__builtins__=scoped)
main=private(prior.main,prepare_install=prepare_install,dispatch=dispatch,launch=launch,
    load_installation=load_installation,prepare_restore=prepare_restore,replay=replay,__builtins__=scoped,__doc__=__doc__)
if __name__=='__main__':main()
