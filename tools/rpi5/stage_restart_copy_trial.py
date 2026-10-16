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
import stage_restart_diagnostic_trial as preceding_diagnostic
import display_restart_copy_media_v1 as engine
from tools.rpi5 import prepare_display_xnu_trial_v2 as graph
from tools.rpi5 import check_display_restart_copy as checker
from tools.rpi5 import restart_copy_serial as protocol

for _name,_value in vars(original).items():
    if not _name.startswith('__') and _name not in ('engine','checker'):
        globals()[_name]=_value
CONTROLLER='restart-copy-config-loader-controller-v1'
PACKAGE=ROOT/'build/rpi5/display-restart-copy-sgf9_m1d'
MANIFEST_SHA='e01f4e177cbb89a0f9b0663a711683de4b7ea92551c8a10a3885b2d1b38b7aa2'
IMAGE_SHA=engine.IMAGE_SHA
TAG='d55b6f18e6ef4b97a22c03e9accde511'
REPORT=ROOT/'build/rpi5/restart-copy-qualification-20261014/checker-report.json'
REPORT_SHA='13aadf72a550868f1497b4ed0469d1f575a01e0846108beed02b40510cc8dd7f'
DESCRIPTOR='restart-copy-fixed33'
_SOURCE_EXPECTATIONS=None

def transport():
    import serial_restart_copy_trial
    import restart_copy_evidence
    import arm_restart_copy_trial
    return restart_copy_evidence

def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(name)!=digest for name,digest in _SOURCE_EXPECTATIONS.items()):
            raise ValueError('Diagnostic transport source changed after inventory')
        return dict(_SOURCE_EXPECTATIONS)
    names=('stage_restart_copy_trial.py','serial_restart_copy_trial.py',
        'restart_copy_evidence.py','arm_restart_copy_trial.py',
        'display_restart_copy_media_v1.py','restart_copy_serial.py',
        'build_display_restart_copy.py','check_display_restart_copy.py',
        'tests/test_restart_copy_transport.py','tests/test_restart_copy_media.py',
        'tests/test_arm_restart_diagnostic_compat_v2.py','arm_restart_diagnostic_compat_v2.py')
    _SOURCE_EXPECTATIONS=original.source_pins()|preceding_diagnostic.source_pins()|graph.source_pins()|engine.source_pins()|{
        str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{str(REPORT):REPORT_SHA}
    if any(sha(name)!=digest for name,digest in _SOURCE_EXPECTATIONS.items()):
        raise ValueError('Diagnostic source inventory did not match actual bytes')
    return dict(_SOURCE_EXPECTATIONS)

def valid_report(report):
    if sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):
        raise ValueError('Exact separately retained diagnostic report required')
    expected=dict(profile='rpi5-display-restart-two-copy-phases-v1',tag=TAG,
        image_sha256=IMAGE_SHA,manifest_sha256=MANIFEST_SHA,package=str(PACKAGE),
        image=str(PACKAGE/'probe.bin'),image_bytes=engine.IMAGE_BYTES,root_nodes=33,root_bytes=2031616,
        root_sha256='56b0e4ce4995e21864f6d5e2bfe43826d7a1d5c0ff83c57244644ff23627cf0e',
        trial_marker='RPI5XNU:DISPLAYRESTART_COPY:ENTRY TAG='+TAG+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',
        root_ready_marker=protocol.ROOT_READY.decode(),root_ready_max_reports=3,
        mirror_ready_marker=protocol.MIRROR.decode(),watchdog_ready_marker=protocol.WATCHDOG.decode(),
        watchdog_ready_profile='root42-state-confirmed-watchdog-kernel-v1',
        restart_ready_marker=protocol.READY.decode(),restart_pre_smc_prefix=protocol.PRE_PREFIX.decode(),
        terminal_watchdog_seconds=180,watchdog_hardware_timeout_seconds=15,
        required_normal_firmware_sha256=engine.GOOD_FW_SHA,
        physical_visibility_proven=False,physical_restart_proven=False,physical_psci_causality_proven=False,
        watchdog_rate_bound_proven=False,watchdog_reloaded_by_diagnostic=False,
        watchdog_deadline_changed=False,poweroff_supported=False,target_executed=False)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()):
        raise ValueError('Exact root33/PSCI/nominal-only/unchanged watchdog report required')
    for key in ('checks','diagnostic_checks','handoff','copy_phase_checks'):
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
    import serial_restart_copy_trial as recorder
    media=checkpoint['payload']['media_plan'];valid_report(media['preflight'])
    engine.bound_core('0'*32).validate_files(media)
    context={'installed':{'preflight':media['preflight']},'evidence':checkpoint['evidence_sha256']}
    sources=recorder.bound_sources(context);package=recorder.package_pins(context)
    if (Path(recorder.capture.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_restart_copy_trial.py' or
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
    import arm_restart_copy_trial as launcher
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
