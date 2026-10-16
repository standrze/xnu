#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One opt-in genuine reboot-path trial; original firmware and fallback retained.

Publication is the unchanged config32/loader algorithm. Nominal early return
is engineering evidence only, not an unconditional exclusion of watchdog reset.
Only the completed diagnostic restoration is admitted as the new baseline.
"""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import stage_display_xnu_trial as original
import stage_restart_init_trial as preceding_diagnostic
import display_restart_late_media_v1 as engine
from tools.rpi5 import prepare_display_xnu_trial_v2 as graph
from tools.rpi5 import check_display_restart_late_framed as checker
from tools.rpi5 import restart_late_serial as protocol

for _name,_value in vars(original).items():
    if not _name.startswith('__') and _name not in ('engine','checker'):
        globals()[_name]=_value
CONTROLLER='restart-late-config-loader-controller-v1'
PACKAGE=ROOT/'build/rpi5/display-restart-late-framed-tquvyn12'
MANIFEST_SHA='80fb3f47301a1d7be2ccc9834706f47feb635b98690e4c9404e383c196b77c2e'
IMAGE_SHA=engine.IMAGE_SHA
TAG='a52ab98358c3409cb560358cd3c79eca'
REPORT=ROOT/'build/rpi5/restart-late-qualification-20261014/checker-report.json'
REPORT_SHA='7fdf307bd644e2f27579250193c021117059255faefdd7e7778fc21d36bf1c16'
DESCRIPTOR='restart-late-fixed33'
_SOURCE_EXPECTATIONS=None

def transport():
    import serial_restart_late_trial
    import restart_late_evidence
    import arm_restart_late_trial
    return restart_late_evidence

def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(name)!=digest for name,digest in _SOURCE_EXPECTATIONS.items()):
            raise ValueError('Diagnostic transport source changed after inventory')
        return dict(_SOURCE_EXPECTATIONS)
    names=('stage_restart_late_trial.py','serial_restart_late_trial.py',
        'restart_late_evidence.py','arm_restart_late_trial.py',
        'display_restart_late_media_v1.py','restart_late_serial.py',
        'build_display_restart_late_framed.py','check_display_restart_late_framed.py',
        'tests/test_display_restart_late_framed.py','tests/test_restart_late_serial.py',
        'tests/test_restart_late_transport.py','tests/test_restart_late_media.py',
        'tests/test_arm_restart_diagnostic_compat_v2.py','arm_restart_diagnostic_compat_v2.py')
    _SOURCE_EXPECTATIONS=original.source_pins()|preceding_diagnostic.source_pins()|graph.source_pins()|engine.source_pins()|{
        str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{str(REPORT):REPORT_SHA}
    if any(sha(name)!=digest for name,digest in _SOURCE_EXPECTATIONS.items()):
        raise ValueError('Diagnostic source inventory did not match actual bytes')
    return dict(_SOURCE_EXPECTATIONS)

def valid_report(report):
    if sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):
        raise ValueError('Exact separately retained diagnostic report required')
    expected=dict(profile='rpi5-display-restart-pid1-late-framed-readiness-v1',tag=TAG,
        image_sha256=IMAGE_SHA,manifest_sha256=MANIFEST_SHA,package=str(PACKAGE),
        image=str(PACKAGE/'probe.bin'),image_bytes=engine.IMAGE_BYTES,root_nodes=33,root_bytes=2031616,
        root_sha256='2245429e4702b20d10c95d93b5b67e8453885016204a13be218d973355b16717',
        trial_marker='RPI5XNU:DISPLAYRESTART_LATE:ENTRY TAG='+TAG+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',
        root_ready_marker=protocol.ROOT_READY.decode(),root_ready_max_reports=3,
        mirror_ready_marker=protocol.MIRROR.decode(),watchdog_ready_marker=protocol.WATCHDOG.decode(),
        watchdog_ready_profile='root42-state-confirmed-watchdog-kernel-v1',
        init_shutdown_ready_marker=protocol.INIT_READY.decode(),init_shutdown_ready_max_reports=3,
        init_readiness_min_successful_sleep_seconds=1,init_readiness_full_mask_revalidated=True,
        init_readiness_newline_framed=True,init_uart_line_atomicity_claimed=False,
        root_only_replaced='/sbin/launchd',
        report_scope='pid1-late-framed-readiness-current-checks-with-historical-components-v1',
        restart_ready_marker=protocol.READY.decode(),restart_pre_smc_prefix=protocol.PRE_PREFIX.decode(),
        terminal_watchdog_seconds=180,watchdog_hardware_timeout_seconds=15,
        required_normal_firmware_sha256=engine.GOOD_FW_SHA,
        physical_visibility_proven=False,physical_restart_proven=False,physical_psci_causality_proven=False,
        watchdog_rate_bound_proven=False,watchdog_reloaded_by_diagnostic=False,
        watchdog_deadline_changed=False,poweroff_supported=False,target_executed=False)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()):
        raise ValueError('Exact root33/PSCI/nominal-only/unchanged watchdog report required')
    for key in ('checks','diagnostic_checks','handoff','copy_phase_checks','init_shutdown_checks'):
        if not report.get(key) or any(v is not True for v in report[key].values()):
            raise ValueError('Complete actual linked diagnostic checks required')
    if not engine.same(report['restart_contract'],dict(cli='/sbin/reboot',options='RB_AUTOBOOT only',
            opt_in='rpi5_psci_restart=1',poweroff_supported=False,physical_restart_proven=False)):
        raise ValueError('Genuine original wrapper and explicit reboot-only opt-in required')
    if not engine.same(report.get('copy_phase_contract'),checker.b.CONTRACT):
        raise ValueError('Exact two copy phases and unchanged watchdog limits required')
    return True

def baseline(directory,seal_sha,plan_sha):
    # Do not silently route the current pair restoration through a stale
    # display/loader reader, nor accept a pending installation as restoration.
    accepted=preceding_diagnostic.restoration(directory,seal_sha,plan_sha)
    files=accepted['result']['publication']['protected_files_sha256']
    if (files.get('config.txt')!=engine.ORIGINAL_CONFIG_SHA or
            files.get('bl31.bin')!=engine.GOOD_FW_SHA or files.get('probe.bin')!=GOOD['probe.bin'][1]):
        raise ValueError('Completed diagnostic original config/normal firmware/zsh restoration required')
    return accepted

def admit(checkpoint):
    import serial_restart_late_trial as recorder
    media=checkpoint['payload']['media_plan'];valid_report(media['preflight'])
    engine.bound_core('0'*32).validate_files(media)
    context={'installed':{'preflight':media['preflight']},'evidence':checkpoint['evidence_sha256']}
    sources=recorder.bound_sources(context);package=recorder.package_pins(context)
    if (Path(recorder.capture.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_restart_late_trial.py' or
            Path(recorder.stage.__file__).resolve()!=Path(__file__).resolve() or
            recorder.protocol is not protocol or recorder.HOST_RETURN_SECONDS!=300):
        raise ValueError('Exact diagnostic receiver and modem-gated namespace required')
    return dict(actual_report_bound=True,actual_recorder_source_members=len(sources),
        actual_recorder_package_members=len(package),serial_input_guarded_by_fresh_mirror_root_prompt=True,
        host_sd_to_nvme_seconds=300,terminal_service_seconds=180,hardware_countdown_seconds=15,
        tx_seconds=120,tx_command_reserve_seconds=45,reboot_command_count=1,
        physical_psci_causality_proven=False,watchdog_fallback_removal_authorized=False,hardware_executed=False)

def get_descriptor(kind):
    if kind!=DESCRIPTOR:raise ValueError('Fixed root33 restart diagnostic only')
    return {'hardware_allowed':True}

def launch(directory,seal_sha,plan_sha,device,capture,output,boot):
    import arm_restart_late_trial as launcher
    return launcher.launch(load_installation(directory,seal_sha,plan_sha),device,capture,output,boot)

# Reuse the literal publisher and narrowly qualified compiler-directory graph
# adapter. No arbitrary path normalization, descriptor imports or remote code.
_graph_scope=dict(vars(graph),stage=sys.modules[__name__])
_package_graph=types.FunctionType(graph.package_graph.__code__,_graph_scope)
_graph_scope['include_directory']=types.FunctionType(graph.include_directory.__code__,_graph_scope)
_preceding=types.SimpleNamespace(**{**vars(original.preceding),'package_graph':_package_graph})
_dispatch=private(original.publisher.dispatch,engine=engine,
    descriptors=types.SimpleNamespace(get=get_descriptor),subprocess=original.upload_transport)
_scope=dict(vars(original),CONTROLLER=CONTROLLER,PACKAGE=PACKAGE,MANIFEST_SHA=MANIFEST_SHA,
    IMAGE_SHA=IMAGE_SHA,TAG=TAG,REPORT=REPORT,REPORT_SHA=REPORT_SHA,engine=engine,checker=checker,
    preceding=_preceding,source_pins=source_pins,transport=transport,baseline=baseline,
    valid_report=valid_report,admit=admit,launch=launch,_dispatch=_dispatch,__file__=__file__,__doc__=__doc__)
# This literal is the only descriptor change in the original preparation body.
_prepare_source=Path(original.__file__).read_text()
_old="descriptor='display-xnu-fixed32'"
if _prepare_source.count(_old)!=1:raise ValueError('Exact original preparation descriptor boundary')
_prepare_source=_prepare_source.replace(_old,'descriptor='+repr(DESCRIPTOR))
_code=compile(_prepare_source,str(Path(__file__).resolve()),'exec')
_prepare_code=next(c for c in _code.co_consts if isinstance(c,types.CodeType) and c.co_name=='prepare_install')
_scope['prepare_install']=types.FunctionType(_prepare_code,_scope)
prepare_install=_scope['prepare_install']
for _name in ('sealed_operation','load_installation','prepare_restore','restoration','dispatch','replay','main'):
    _fn=getattr(original,_name)
    _scope[_name]=types.FunctionType(_fn.__code__,_scope,argdefs=_fn.__defaults__)
    globals()[_name]=_scope[_name]

if __name__=='__main__':raise SystemExit(main())


