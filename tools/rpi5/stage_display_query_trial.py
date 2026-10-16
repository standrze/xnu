#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One fixed bounded display GET query and original single-loader publisher.

No PCIe/XNU marker admission. Separate DISPLAYGET receive-only evidence is required
before explicit restoration; known-good/current rollback safeguards unchanged.
No allocation, SET request, framebuffer access, drawing or XNU transfer.
"""
import inspect
import json
from pathlib import Path
import sys
import types
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import stage_root42_pthread_trial as base
import stage_framebuffer_observation_trial_v2 as previous
import gem_selected_trial_v1 as paired
import prepare_root42_pthread_trial_v3 as graph
from tools.rpi5 import check_display_query_package as checker

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private,engine,GOOD=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private','engine','GOOD'))
CONTROLLER='display-get-standalone-single-loader-v1'
PACKAGE=ROOT/'build/rpi5/display-query-7m77tyrn'
MANIFEST_SHA='235386b7b60ee870d86becc1f922c9b0219781824ab0a7a1f49c2c935b84b2df'
IMAGE_SHA='ccd94caac86ea0ef0696631795c2c0630b4df3d711cd2461bd60944f6f733916'
TAG='34a3d8fd702141d992c4da5ab5ff1dc3'
def baseline(directory,seal_sha,plan_sha):
    return paired.baseline(directory,seal_sha,plan_sha)
prior=types.SimpleNamespace(**{**vars(base.prior),'package_graph':graph.package_graph,'baseline':baseline})
def transport():
    import serial_display_query_trial
    import display_query_evidence
    import arm_display_query_reboot
    return display_query_evidence
def source_pins():
    names=('stage_display_query_trial.py','serial_display_query_trial.py',
        'display_query_evidence.py','arm_display_query_reboot.py','tests/test_display_query_transport.py',
        'build_display_query_package.py','check_display_query_package.py','display_query_serial.py',
        'tests/test_display_query_serial.py','tests/test_display_query_adapter.py','tests/test_display_query_package.py',
        'tests/test_framebuffer_observation_serial.py','arm_pcie_trace_reboot.py','tests/test_arm_pcie_trace_reboot.py')
    return previous.source_pins()|paired.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}
def valid_report(report):
    if (report.get('profile')!='pi5-display-get-standalone-v1' or report.get('tag')!=TAG or
        report.get('image_sha256')!=IMAGE_SHA or report.get('manifest_sha256')!=MANIFEST_SHA or
        report.get('image')!=str(PACKAGE/'probe.bin') or report.get('image_bytes')!=59456 or
        report.get('package')!=str(PACKAGE) or report.get('loader_live')!={'start':0x9000000,'end':152304656} or
        report.get('query_storage')!={'start':151060480,'bytes':12288} or report.get('early_diagnostic_stages')!=19 or
        report.get('output_limit_bytes')!=32768 or report.get('query_contract')!=checker.b.contract() or
        report.get('required_normal_firmware_sha256')!=engine.original.FIRMWARE_SHA or
        report.get('mailbox_get_transport_authored') is not True or
        not report.get('checks') or any(value is not True for value in report['checks'].values()) or
        report.get('watchdog')!=dict(already_active_required=True,countdown_write_once_seconds=15,
            software_output_seconds=8,reset_route_writes=False,reload_after_arm=False) or
        any(report.get(k) is not False for k in ('physical_execution','installation_admitted','ownership_proven','scanout_cache_contract_proven',
            'framebuffer_access','allocation','drawing'))):
        raise ValueError('Exact checked raw GET-only package report required')
    return True
scope={**vars(base),**{n:globals()[n] for n in ('CONTROLLER','PACKAGE','MANIFEST_SHA','IMAGE_SHA','prior','checker','transport','source_pins','valid_report')},
    '__file__':__file__,'__doc__':__doc__}
source=inspect.getsource(base.prepare_install)
old="report['image_sha256']!=IMAGE_SHA or report['root_nodes']!=42 or report['root_files']!=30"
if source.count(old)!=1:raise ValueError('Fixed original publisher package boundary changed')
exec(compile(source.replace(old,'not valid_report(report)'),__file__,'exec'),scope)
_prepare_install=scope['prepare_install']
for name in ('sealed_operation','load_installation','prepare_restore','restoration','dispatch','_dispatch','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]
# Only the exact original candidate upload gains compression and a longer
# finite bound. All SSH/remote SD source/intent paths remain canonical.
def upload_run(command,**kwargs):
    if command and command[0]=='scp':
        prefix=['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
        if not isinstance(command,list) or len(command)!=9 or command[:7]!=prefix or kwargs!={'check':True,'timeout':60}:
            raise ValueError('Exact original bounded candidate-upload call required')
        command=[command[0],'-C',*command[1:]];kwargs=dict(kwargs,timeout=180)
    return subprocess.run(command,**kwargs)
upload_transport=types.SimpleNamespace(run=upload_run)
scope['subprocess']=upload_transport
_base_restore=prepare_restore
def prepare_restore(directory,seal_sha,plan_sha,capture):
    # Preserve the actual byte-timing journal in the final restoration closure,
    # not only its digest inside the return receipt.
    checkpoint,pin,metrics=_base_restore(directory,seal_sha,plan_sha,capture)
    journal=str(local(capture)/'receive-events.jsonl');digest=sha(journal)
    pins=prior.merge_pins(checkpoint['evidence_sha256'],{journal:digest})
    payload=checkpoint['payload']
    checkpoint,pin=seals.create(lambda:payload,pins)
    metrics['closure_files']=len(pins)
    metrics['journal_seal_extension_calls']=1
    return checkpoint,pin,metrics
scope['prepare_restore']=prepare_restore
def admit(checkpoint):
    import serial_display_query_trial as recorder
    context={'installed':{'preflight':checkpoint['payload']['media_plan']['preflight']},'evidence':checkpoint['evidence_sha256']}
    valid_report(context['installed']['preflight']);sources=recorder.bound_sources(context);packages=recorder.package_pins(context)
    return dict(actual_recorder_source_members=len(sources),actual_recorder_package_members=len(packages),
        actual_report_bound=True,zero_serial_input=True,hardware_executed=False)
def prepare_install(directory,prior_seal,prior_plan,boot,package=PACKAGE):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,boot,package)
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics
scope['prepare_install']=prepare_install
def replay(directory,seal_sha,plan_sha,capture,restored_directory,restore_seal,restore_plan):
    evidence=transport();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    restored=restoration(restored_directory,restore_seal,restore_plan)
    if pin!=restore_seal or not engine.same(restored['checkpoint'],expected) or restored['result']['publication']['identity']['boot_id']!=boot:
        raise ValueError('Explicit restoration does not derive from exact observer/return')
    return dict(format='rpi5-display-query-chain-replay-v1',capture_valid=returned['capture_valid'],
        diagnostic=returned['diagnostic'],capture_error=returned['capture_error'],
        independent_normal_nvme_linux_return_verified=True,returned_linux_boot_id=boot,working_loader_restored=True,
        firmware_unchanged=True,ownership_proven=False,scanout_cache_contract_proven=False,drawing=False,mirror_enabled=False,
        historical_catalog_counts=[len(context['plan']['historical_catalog']),len(context['result']['next_catalog']),len(restored['result']['next_catalog'])],
        historical_archives_reverified=False,fresh_hardware_observation=False,compiler_calls=0)
scope['replay']=replay
if __name__=='__main__':raise SystemExit(main())
