#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One fixed FDT observer, normal firmware, original single-loader publisher.

No PCIe/XNU marker admission. Separate FBOBS receive-only evidence is required
before explicit restoration; known-good/current rollback safeguards unchanged.
"""
import importlib
import inspect
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import stage_root42_pthread_trial as base
import stage_framebuffer_observation_trial_v2 as previous
import prepare_root42_pthread_trial_v3 as graph
from tools.rpi5 import check_framebuffer_diagnostic as checker

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private,engine,GOOD=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private','engine','GOOD'))
CONTROLLER='framebuffer-fdt-precheck-diagnostic-single-loader-v1'
PACKAGE=ROOT/'build/rpi5/framebuffer-diagnostic-j0vcgsfv'
MANIFEST_SHA='0e7310cd7aaa09e057e7d13538f1bb45b12e0bad11e39e8920f1c5bd94454169'
IMAGE_SHA='4a6d4236e2ee0c13993450e77c6dcdacf6443a3b2bcaa949bcba5a7d80aa0449'
TAG='75455aec122849d988c3afc133327d47'
def baseline(directory,seal_sha,plan_sha):
    plan=json.loads((local(directory)/'plan.json').read_text())
    if plan['media']['profile']!=engine.RESTORE or plan['media'].get('controller')!=previous.CONTROLLER:
        raise ValueError('Completed exact observation-v2 single-loader restoration required')
    return previous.restoration(directory,seal_sha,plan_sha)
prior=types.SimpleNamespace(**{**vars(base.prior),'package_graph':graph.package_graph,'baseline':baseline})
def transport():
    import serial_framebuffer_diagnostic_trial
    import framebuffer_diagnostic_evidence
    import arm_framebuffer_diagnostic_reboot
    return framebuffer_diagnostic_evidence
def source_pins():
    names=('stage_framebuffer_diagnostic_trial.py','serial_framebuffer_diagnostic_trial.py',
        'framebuffer_diagnostic_evidence.py','arm_framebuffer_diagnostic_reboot.py','tests/test_framebuffer_diagnostic_transport.py',
        'build_framebuffer_diagnostic.py','check_framebuffer_diagnostic.py','framebuffer_diagnostic_serial.py',
        'tests/test_framebuffer_diagnostic_serial.py','tests/test_framebuffer_diagnostic_guard.py','tests/test_framebuffer_diagnostic_package.py',
        'tests/test_framebuffer_observation_serial.py','arm_pcie_trace_reboot.py','tests/test_arm_pcie_trace_reboot.py')
    return previous.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}
def valid_report(report):
    if (report.get('profile')!='pi5-framebuffer-fdt-precheck-diagnostic-v1' or report.get('tag')!=TAG or
        report.get('image_sha256')!=IMAGE_SHA or report.get('manifest_sha256')!=MANIFEST_SHA or
        report.get('image')!=str(PACKAGE/'probe.bin') or report.get('image_bytes')!=52288 or
        report.get('loader_live')!={'start':0x9000000,'end':151219024} or
        report.get('early_diagnostic_stages')!=19 or report.get('early_uart_firmware_preserved') is not True or
        report.get('precheck_rejection_is_observation') is not False or
        report.get('watchdog')!=dict(already_active_required=True,countdown_write_once_seconds=15,
            software_output_seconds=8,reset_route_writes=False,reload_after_arm=False) or
        any(report.get(k) is not False for k in ('physical_execution','installation_admitted','ownership_proven','scanout_cache_contract_proven'))):
        raise ValueError('Exact checked FDT-only observer report required')
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
    import serial_framebuffer_diagnostic_trial as recorder
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
    return dict(format='rpi5-framebuffer-diagnostic-chain-replay-v1',capture_valid=returned['capture_valid'],
        diagnostic=returned['diagnostic'],capture_error=returned['capture_error'],
        independent_normal_nvme_linux_return_verified=True,returned_linux_boot_id=boot,working_loader_restored=True,
        firmware_unchanged=True,ownership_proven=False,scanout_cache_contract_proven=False,drawing=False,mirror_enabled=False,
        historical_catalog_counts=[len(context['plan']['historical_catalog']),len(context['result']['next_catalog']),len(restored['result']['next_catalog'])],
        historical_archives_reverified=False,fresh_hardware_observation=False,compiler_calls=0)
scope['replay']=replay
if __name__=='__main__':raise SystemExit(main())
