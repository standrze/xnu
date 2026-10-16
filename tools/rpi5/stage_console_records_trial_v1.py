#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current restoration -> sealed console-record trial -> exact restoration.

This controller publishes only config.txt and probe.bin.  Normal firmware is
protected. Unknown publication/reboot outcomes are never retried.
"""
from pathlib import Path
import json,sys,types
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import stage_display_xnu_trial as original
import stage_gem_cpu_batch_trial_v1 as preceding
import display_console_records_media_v1 as engine
from tools.rpi5 import prepare_display_xnu_trial_v2 as graph
from tools.rpi5 import check_display_console_records as actual_checker
from tools.rpi5 import console_records_serial as protocol

for _name,_value in vars(original).items():
    if not _name.startswith('__') and _name not in ('engine','checker','preceding','prior'):
        globals()[_name]=_value
prior=preceding
ROOT=preceding.ROOT
CONTROLLER='console-records-config-loader-controller-v1'
PACKAGE=ROOT/'build/rpi5/display-console-records-691ku6u6'
MANIFEST_SHA='f32e6b5a155d1869b51511db4993d3298765914bba2cf59784108922d38b6cb1'
IMAGE_SHA=engine.IMAGE_SHA
TAG='b8f942ef8e1543b0b962f5bb7797df1b'
REPORT=ROOT/'build/rpi5/display-console-records-qualification-20261014/checker-report.json'
REPORT_SHA='468b260622e64ce600858fe31f25da7f00bf05814c87453be1b531533495e575'
DESCRIPTOR='console-records-fixed33'
BASELINE=ROOT/'build/rpi5/gem-cpu-batch-restored-20261014'
BASELINE_SEAL='cda1ffe9a482dcb8db9729025956c40fe81ae57ebf0276bfc1cdca90310b5af1'
BASELINE_PLAN='87822332e49a0e76bfaff2d1b6dff8320942dd3f3e90a8bcb9297d1247e56690'
BASELINE_BOOT='1fd308fa-08e5-4aa1-9799-86939ac251aa'
BASELINE_CATALOG=466
CONFIG=ROOT/'build/rpi5/display-allocate-config32-20261013/config.txt'
GOOD={'config.txt':(ROOT/'build/rpi5/gate2-config.txt',engine.ORIGINAL_CONFIG_SHA,len(engine.ORIGINAL_CONFIG)),
      'probe.bin':preceding.GOOD['probe.bin']}
_SOURCE_EXPECTATIONS=None

_graph_scope=dict(vars(graph),stage=sys.modules[__name__])
_graph_scope['include_directory']=types.FunctionType(graph.include_directory.__code__,_graph_scope)
package_graph=types.FunctionType(graph.package_graph.__code__,_graph_scope)

class checker:
    @staticmethod
    def inspect(package):return actual_checker.inspect(package,MANIFEST_SHA)

def transport():
    import serial_console_records_trial_v1,console_records_evidence_v1,arm_console_records_reboot_v1
    return console_records_evidence_v1

def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Console-record transport source changed after inventory')
        return dict(_SOURCE_EXPECTATIONS)
    names=('stage_console_records_trial_v1.py','serial_console_records_trial_v1.py','console_records_evidence_v1.py',
        'arm_console_records_reboot_v1.py','display_console_records_media_v1.py','console_records_serial.py',
        'tests/test_console_records_transport_v1.py','build_display_console_records.py','check_display_console_records.py',
        'console_record_profile.py','tests/test_console_records.py','tests/test_display_console_records.py')
    _SOURCE_EXPECTATIONS=preceding.source_pins()|engine.source_pins()|{
        str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{
        str(CONFIG):engine.TRIAL_CONFIG_SHA,str(GOOD['config.txt'][0]):engine.ORIGINAL_CONFIG_SHA,str(REPORT):REPORT_SHA}
    if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Console-record source inventory differs')
    return dict(_SOURCE_EXPECTATIONS)

def valid_report(report):
    if sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):raise ValueError('Exact retained console report required')
    expected=dict(profile='rpi5-safe-thread-console-records-v1',package=str(PACKAGE),manifest_sha256=MANIFEST_SHA,
        image=str(PACKAGE/'probe.bin'),image_sha256=IMAGE_SHA,image_bytes=engine.IMAGE_BYTES,tag=TAG,
        trial_marker='RPI5XNU:DISPLAY_CONSOLE_RECORDS:ENTRY TAG='+TAG+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',
        root_nodes=33,root_bytes=2031616,root_sha256='f5829ee8628325cd52c3ddde7c97e6389d84f1b55b079dc17c0e9dd97e753631',
        root_ready_marker=protocol.ROOT_READY.decode(),root_ready_max_reports=3,mirror_ready_marker=protocol.MIRROR.decode(),
        watchdog_ready_marker=protocol.WATCHDOG.decode(),watchdog_ready_profile='root42-state-confirmed-watchdog-kernel-v1',
        init_shutdown_ready_marker=protocol.INIT_READY.decode(),init_shutdown_ready_max_reports=3,
        restart_ready_marker=protocol.READY.decode(),restart_pre_smc_prefix=protocol.PRE_PREFIX.decode(),
        terminal_watchdog_seconds=180,watchdog_hardware_timeout_seconds=15,
        required_normal_firmware_sha256=engine.GOOD_FW_SHA,report_scope='safe-normal-console-current-with-explicit-historical-components-v1',
        physical_visibility_proven=False,physical_restart_proven=False,physical_psci_causality_proven=False,
        watchdog_rate_bound_proven=False,watchdog_reloaded_by_diagnostic=False,watchdog_deadline_changed=False,
        poweroff_supported=False,target_executed=False)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()):raise ValueError('Exact console-record report fields required')
    if not report.get('checks') or any(v is not True for v in report['checks'].values()):raise ValueError('Complete linked console checks required')
    contract=report.get('console_record_contract',{})
    for key in ('normal_thread_kprintf_before_irq_mask','original_apple_printbuf_and_ring','pl011_check_dr_nonblocking_single_cas',
            'terminal_thread_callout_only','terminal_callout_armed_before_enqueue','restart_presmc_raw_unchanged'):
        if contract.get(key) is not True:raise ValueError('Required console serialization contract absent')
    if contract.get('all_output_atomicity_claimed') is not False or contract.get('target_executed') is not False:
        raise ValueError('Overclaimed console report')
    return True

def baseline(directory,seal_sha,plan_sha):
    if Path(directory).resolve()!=BASELINE or seal_sha!=BASELINE_SEAL or plan_sha!=BASELINE_PLAN:raise ValueError('Exact current466 restoration required')
    accepted=preceding.restoration(directory,seal_sha,plan_sha);publication=accepted['result']['publication']
    files=publication['protected_files_sha256']
    if (publication['identity']['boot_id']!=BASELINE_BOOT or len(accepted['result']['next_catalog'])!=BASELINE_CATALOG or
            files.get('config.txt')!=engine.ORIGINAL_CONFIG_SHA or files.get('bl31.bin')!=engine.GOOD_FW_SHA or
            files.get('probe.bin')!=GOOD['probe.bin'][1]):raise ValueError('Current466 normal config/firmware/zsh restoration required')
    return accepted

def admit(checkpoint):
    import serial_console_records_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];valid_report(media['preflight']);engine.bound_core('0'*32).validate_files(media)
    context={'installed':{'preflight':media['preflight']},'evidence':checkpoint['evidence_sha256']}
    sources=recorder.bound_sources(context);package=recorder.package_pins(context)
    if (Path(recorder.capture.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_console_records_trial_v1.py' or
            Path(recorder.stage.__file__).resolve()!=Path(__file__).resolve() or recorder.protocol is not protocol or recorder.HOST_RETURN_SECONDS!=300):
        raise ValueError('Exact console-record receiver namespace required')
    return dict(actual_report_bound=True,actual_recorder_source_members=len(sources),actual_recorder_package_members=len(package),
        serial_input_guarded_by_fresh_mirror_root_prompt=True,clean_pid1_reports_required=True,clean_watchdog_readiness_required=True,
        host_sd_to_nvme_seconds=300,terminal_service_seconds=180,hardware_countdown_seconds=15,tx_seconds=120,
        tx_command_reserve_seconds=45,reboot_command_count=1,physical_psci_causality_proven=False,hardware_executed=False)

def get_descriptor(kind):
    if kind!=DESCRIPTOR:raise ValueError('Fixed console-record trial only')
    return {'hardware_allowed':True}

def launch(directory,seal_sha,plan_sha,device,capture,output,boot):
    import arm_console_records_reboot_v1 as launcher
    return launcher.launch(load_installation(directory,seal_sha,plan_sha),device,capture,output,boot)

def replay(directory,seal_sha,plan_sha,capture,restored_directory,restore_seal,restore_plan):
    evidence=transport();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    restored=restoration(restored_directory,restore_seal,restore_plan)
    if pin!=restore_seal or not engine.same(restored['checkpoint'],expected) or restored['result']['publication']['identity']['boot_id']!=boot:
        raise ValueError('Restoration not derived from exact console trial and Linux return')
    return dict(format='rpi5-display-console-records-config-loader-chain-v1',capture_valid=returned['capture_valid'],
        diagnostic=returned['diagnostic'],capture_error=returned['capture_error'],original_config_and_loader_restored=True,
        normal_firmware_unchanged=True,independent_normal_nvme_linux_return_verified=True,linux_boot_id=boot,
        framebuffer_authority=True,physical_visibility_proven=False,visual_confirmation_required=False,compiler_calls=0,
        historical_archives_reverified=False,historical_catalog_counts=[len(context['plan']['historical_catalog']),
            len(context['result']['next_catalog']),len(restored['result']['next_catalog'])])

_preceding=types.SimpleNamespace(**{**vars(preceding),'package_graph':package_graph})
_dispatch=private(original.publisher.dispatch,engine=engine,descriptors=types.SimpleNamespace(get=get_descriptor),subprocess=original.upload_transport)
_scope=dict(vars(original),CONTROLLER=CONTROLLER,PACKAGE=PACKAGE,MANIFEST_SHA=MANIFEST_SHA,IMAGE_SHA=IMAGE_SHA,TAG=TAG,
    REPORT=REPORT,REPORT_SHA=REPORT_SHA,engine=engine,checker=checker,preceding=_preceding,prior=preceding,
    source_pins=source_pins,transport=transport,baseline=baseline,valid_report=valid_report,admit=admit,
    launch=launch,replay=replay,get_descriptor=get_descriptor,_dispatch=_dispatch,__file__=__file__,__doc__=__doc__)
_prepare_source=Path(original.__file__).read_text();_old="descriptor='display-xnu-fixed32'"
if _prepare_source.count(_old)!=1:raise ValueError('Exact preparation descriptor boundary')
_prepare_source=_prepare_source.replace(_old,'descriptor='+repr(DESCRIPTOR))
_code=compile(_prepare_source,str(Path(__file__).resolve()),'exec')
_prepare_code=next(c for c in _code.co_consts if isinstance(c,types.CodeType) and c.co_name=='prepare_install')
_derived_prepare=types.FunctionType(_prepare_code,_scope)
def prepare_install(directory,prior_seal,prior_plan,boot):
    if boot!=BASELINE_BOOT:raise ValueError('Exact current Linux boot witness required')
    return _derived_prepare(directory,prior_seal,prior_plan,boot)
_scope['prepare_install']=prepare_install
for _name in ('sealed_operation','load_installation','prepare_restore','restoration','dispatch','main'):
    _fn=getattr(original,_name);_scope[_name]=types.FunctionType(_fn.__code__,_scope,argdefs=_fn.__defaults__);globals()[_name]=_scope[_name]

if __name__=='__main__':raise SystemExit(main())
