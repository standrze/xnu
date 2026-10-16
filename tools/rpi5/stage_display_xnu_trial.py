#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact temporary config32 + same-boot XNU console image; explicit rollback.

All publication operations use the separately sealed config/loader engine.
No firmware/config mutation is performed outside its journaled canonical body.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import gem_capabilities_trial_v1 as preceding
import stage_display_compact_trial as previous_compact
import stage_display_query_trial as observer
import stage_link_trial_v2 as publisher
import display_xnu_media_v1 as engine
from tools.rpi5 import check_display_xnu_console as checker
prior=preceding
ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private=(getattr(preceding,n) for n in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private'))
CONTROLLER='display-xnu-config-loader-controller-v1'
PACKAGE=ROOT/'build/rpi5/display-xnu-console-5cd94fg_'
MANIFEST_SHA='d1c6ce8f6b7ed198a237d367ed821e636f0e073fdf97be8d41212afed497a165'
IMAGE_SHA=engine.IMAGE_SHA
TAG='241f83f874a94488b7c821a82b34c474'
REPORT=ROOT/'build/rpi5/display-xnu-console-qualification-20261014/checker-report.json'
REPORT_SHA='8b93a997c21c6ec0bfd23c4338c92ffd40cc963a207c1c1dd595b08b0e5e1b2a'
CONFIG=ROOT/'build/rpi5/display-allocate-config32-20261013/config.txt'
GOOD={'config.txt':(ROOT/'build/rpi5/gate2-config.txt',engine.ORIGINAL_CONFIG_SHA,len(engine.ORIGINAL_CONFIG)),
      'probe.bin':preceding.GOOD['probe.bin']}

def transport():
    import serial_display_xnu_trial
    import display_xnu_evidence
    import arm_display_xnu_reboot
    return display_xnu_evidence

def source_pins():
    names=('stage_display_xnu_trial.py','serial_display_xnu_trial.py','display_xnu_evidence.py',
        'arm_display_xnu_reboot.py','display_xnu_media_v1.py',
        'tests/test_display_xnu_media_v1.py','tests/test_display_xnu_transport.py',
        'build_display_xnu_console.py','check_display_xnu_console.py','display_xnu_serial.py',
        'tests/test_display_xnu_console_package.py','tests/test_display_xnu_serial.py')
    return preceding.source_pins()|observer.source_pins()|previous_compact.source_pins()|engine.source_pins()|{
        str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{
        str(CONFIG):engine.TRIAL_CONFIG_SHA,str(GOOD['config.txt'][0]):engine.ORIGINAL_CONFIG_SHA,
        str(REPORT):REPORT_SHA}

def valid_report(report):
    from tools.rpi5 import display_xnu_serial as protocol
    if sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):
        raise ValueError('Exact independently checked retained report required')
    expected=dict(profile='pi5-display-xnu-sameboot-console-v1',tag=TAG,image_sha256=IMAGE_SHA,
        manifest_sha256=MANIFEST_SHA,package=str(PACKAGE),image=str(PACKAGE/'probe.bin'),
        image_bytes=engine.IMAGE_BYTES,root_nodes=32,root_bytes=1916928,
        root_sha256='3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27',
        root_ready_marker=protocol.ROOT_READY.decode(),root_ready_max_reports=3,
        watchdog_ready_marker=protocol.WATCHDOG.decode(),watchdog_ready_profile='root42-state-confirmed-watchdog-kernel-v1',
        mirror_ready_marker=protocol.MIRROR.decode(),
        trial_marker='RPI5XNU:DISPLAYXNU:ENTRY TAG='+TAG+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',
        required_normal_firmware_sha256=engine.GOOD_FW_SHA)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()) or not report.get('checks') or any(v is not True for v in report['checks'].values()):
        raise ValueError('Exact same-boot framebuffer/XNU/unchanged32-root package required')
    if not engine.same(report.get('terminal_watchdog_seconds'),180) or not engine.same(report.get('watchdog_hardware_timeout_seconds'),15):
        raise ValueError('Unchanged finite180s terminal plus15s countdown required')
    if report.get('physical_visibility_proven') is not False or report['checks'].get('unchanged_bounded_watchdog') is not True:
        raise ValueError('No physical visibility or extended runtime claim admitted')
    if not all(report.get('handoff',{}).get(k) is True for k in ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string')):
        raise ValueError('Actual retained-FDT handoff required')
    return True

def baseline(directory,seal_sha,plan_sha):
    accepted=previous_compact.restoration(directory,seal_sha,plan_sha)
    files=accepted['result']['publication']['protected_files_sha256']
    if files.get('config.txt')!=engine.ORIGINAL_CONFIG_SHA or any(files.get(n)!=v[1] for n,v in preceding.GOOD.items()):
        raise ValueError('Completed compact config/loader restoration of original config/firmware/zsh required')
    return accepted

def admit(checkpoint):
    import serial_display_xnu_trial as recorder
    media=checkpoint['payload']['media_plan'];valid_report(media['preflight'])
    engine.bound_core('0'*32).validate_files(media)
    context={'installed':{'preflight':media['preflight']},'evidence':checkpoint['evidence_sha256']}
    sources=recorder.bound_sources(context);package=recorder.package_pins(context)
    return dict(actual_report_bound=True,actual_recorder_source_members=len(sources),
        actual_recorder_package_members=len(package),serial_input_guarded_by_fresh_mirror_root_prompt=True,hardware_executed=False)

def prepare_install(directory,prior_seal,prior_plan,boot):
    start=time.monotonic();transport();accepted=baseline(directory,prior_seal,prior_plan)
    if CONFIG.read_bytes()!=engine.TRIAL_CONFIG or GOOD['config.txt'][0].read_bytes()!=engine.ORIGINAL_CONFIG:
        raise ValueError('Exact retained original and derived config32 bytes required')
    pins=preceding.merge_pins(accepted['evidence'],preceding.package_graph(PACKAGE,accepted['evidence']),
        source_pins(),publisher.loaded_sources())
    def audit():
        if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux UUID required')
        if sha(PACKAGE/'manifest.json')!=MANIFEST_SHA:raise ValueError('Exact frozen allocation package required')
        report=checker.inspect(PACKAGE);valid_report(report)
        publication=accepted['result']['publication'];current=dict(publication['protected_files_sha256'])
        rows=accepted['result']['next_catalog'];binding=copy.deepcopy(accepted['plan']['media']['identity_binding'])
        if boot!=publication['identity']['boot_id']:binding['linux_boot_id_before_write']=publication['identity']['boot_id']
        binding['linux_boot_id_after_write']=boot
        if binding['linux_boot_id_before_write']==boot:raise ValueError('Distinct preceding Linux witness required')
        files=[];candidates={}
        new={'config.txt':(CONFIG,engine.TRIAL_CONFIG_SHA,len(engine.TRIAL_CONFIG)),
             'probe.bin':(PACKAGE/'probe.bin',IMAGE_SHA,engine.IMAGE_BYTES)}
        for name,(path,digest,size) in GOOD.items():
            if sha(path)!=digest or path.stat().st_size!=size or current.pop(name)!=digest:raise ValueError('Original config/loader changed')
            target,h,n=new[name];files.append(dict(target=name,candidate='candidate-'+name,
                old_sha256=digest,old_bytes=size,new_sha256=h,new_bytes=n));candidates[name]=str(target)
        media=dict(host=HOST,profile=engine.TRIAL,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
            protected_files=current,protected_sha256={n:r['sha256'] for n,r in publication['protected_after'].items()},
            nvme_backups=rows,descriptor='display-xnu-fixed32',preflight=report,package=str(PACKAGE),
            source_sha256=source_pins(),controller=CONTROLLER,
            ancestry=dict(directory=accepted['directory'],checkpoint_sha256=prior_seal,plan_sha256=prior_plan,
                hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')}),
            no_firmware_change=True,exact_temporary_config32=True,no_hfs_mount=True,no_reboot=True,
            no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
        engine.bound_core('0'*32).validate_files(media)
        if any(pins.get(n)!=h for n,h in publisher.loaded_sources().items()):raise ValueError('Unsealed audit dependency')
        return dict(media_plan=media,history_catalog=rows,baseline_paths=accepted['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    metrics=dict(full_audit_calls=1,package_semantic_audit_calls=1,package_compiler_audit_calls=0,historical_semantic_audit_calls=0,
        closure_files=len(pins),full_audit_and_seal_seconds=time.monotonic()-start,
        historical_archives_reverified=False,prior_catalog_count=len(accepted['result']['next_catalog']))
    metrics['recorder_admission']=admit(checkpoint);return checkpoint,pin,metrics

def sealed_operation(directory,seal_sha,plan_sha,profile):
    directory=local(directory);checkpoint=json.loads((directory/'checkpoint.json').read_text())
    payload=seals.revalidate(checkpoint,seal_sha);plan=json.loads((directory/'plan.json').read_text())
    result=json.loads((directory/'result.json').read_text())
    if plan['media']['profile']!=profile or plan['media'].get('controller')!=CONTROLLER:raise ValueError('Exact allocation config-loader operation required')
    exact,pin=engine.plan_from_seal(checkpoint,seal_sha,profile,plan['tag'],plan['media']['run'],payload['media_plan'])
    if pin!=plan_sha or not engine.same(exact,plan):raise ValueError('Canonical config-loader plan differs')
    engine.validate_result(result,plan,plan_sha)
    if any(checkpoint['evidence_sha256'].get(n)!=h for n,h in source_pins().items()):raise ValueError('Complete sealed allocation transport closure required')
    pins=dict(checkpoint['evidence_sha256'])
    for name in ('checkpoint.json','plan.json','result.json'):pins[str(directory/name)]=sha(directory/name)
    return dict(directory=str(directory),checkpoint=checkpoint,plan=plan,result=result,evidence=pins)

def load_installation(directory,seal_sha,plan_sha):
    transport();context=sealed_operation(directory,seal_sha,plan_sha,engine.TRIAL);media=context['plan']['media']
    valid_report(media['preflight'])
    context['installed']=dict(directory=context['directory'],checkpoint_sha256=seal_sha,plan_sha256=plan_sha,
        result_sha256=sha(local(directory)/'result.json'),preflight=media['preflight'],loader_sha256=IMAGE_SHA,
        config_sha256=engine.TRIAL_CONFIG_SHA,original_linux_boot_id=media['linux_boot_id'])
    return context

def prepare_restore(directory,seal_sha,plan_sha,capture):
    evidence=transport();start=time.monotonic();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);old=context['plan']['media'];publication=context['result']['publication']
    rows=context['result']['next_catalog'];media=copy.deepcopy(old);media.pop('run')
    media.update(profile=engine.RESTORE,linux_boot_id=boot,nvme_backups=rows,files=[],candidates={})
    media['identity_binding'].update(linux_boot_id_before_write=old['linux_boot_id'],linux_boot_id_after_write=boot)
    protected=dict(publication['protected_files_sha256'])
    for row in old['files']:
        name=row['target'];path,h,size=GOOD[name]
        if protected.pop(name)!=row['new_sha256'] or sha(path)!=h or path.stat().st_size!=size:raise ValueError('Exact original config/loader restore bytes required')
        media['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=row['new_sha256'],old_bytes=row['new_bytes'],new_sha256=h,new_bytes=size))
        media['candidates'][name]=str(path)
    media['protected_files']=protected;media['protected_sha256']={n:r['sha256'] for n,r in publication['protected_after'].items()}
    media['ancestry']=dict(directory=str(local(directory)),hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')},
        return_sha256=sha(local(capture)/'return.json'))
    pins=preceding.merge_pins(context['evidence'],{str(local(capture)/n):sha(local(capture)/n)
        for n in ('armed.json','state.json','serial.bin','receive-events.jsonl','return.json')})
    def audit():
        if not engine.same(list(evidence.load_return(context,capture)),[returned,boot]):raise ValueError('Independent Linux return changed')
        engine.bound_core('0'*32).validate_files(media)
        return dict(media_plan=media,history_catalog=rows,baseline_paths=context['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    return checkpoint,pin,dict(full_audit_calls=1,package_compiler_audit_calls=0,historical_semantic_audit_calls=0,
        full_audit_and_seal_seconds=time.monotonic()-start,closure_files=len(pins),historical_archives_reverified=False)

def restoration(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    files=context['result']['publication']['protected_files_sha256']
    if files.get('bl31.bin')!=engine.GOOD_FW_SHA or any(files.get(n)!=v[1] for n,v in GOOD.items()):raise ValueError('Original config/normal firmware/zsh not restored')
    return context

def upload_run(command,**kwargs):return preceding.upload_run(command,**kwargs)
upload_transport=types.SimpleNamespace(run=upload_run)
def get_descriptor(kind):
    if kind!='display-xnu-fixed32':raise ValueError('Fixed display allocation transport only')
    return {'hardware_allowed':True}
_dispatch=private(publisher.dispatch,engine=engine,descriptors=types.SimpleNamespace(get=get_descriptor),subprocess=upload_transport)
def dispatch(checkpoint,seal_sha,out,metrics,execute=False):
    media=seals.revalidate(checkpoint,seal_sha)['media_plan']
    if media.get('controller')!=CONTROLLER:raise ValueError('Exact config-loader controller required')
    admit(checkpoint)
    with lease.hold(ROOT,'display-xnu-config-loader-v1') if execute else __import__('contextlib').nullcontext():
        return _dispatch(checkpoint,seal_sha,out,metrics,execute)

def launch(directory,seal_sha,plan_sha,device,capture,output,boot):
    import arm_display_xnu_reboot as launcher
    return launcher.launch(load_installation(directory,seal_sha,plan_sha),device,capture,output,boot)

def replay(directory,seal_sha,plan_sha,capture,restored_directory,restore_seal,restore_plan):
    evidence=transport();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    restored=restoration(restored_directory,restore_seal,restore_plan)
    if pin!=restore_seal or not engine.same(restored['checkpoint'],expected) or restored['result']['publication']['identity']['boot_id']!=boot:
        raise ValueError('Restoration not derived from exact allocation trial and Linux return')
    return dict(format='rpi5-display-xnu-config-loader-chain-v1',capture_valid=returned['capture_valid'],
        diagnostic=returned['diagnostic'],capture_error=returned['capture_error'],original_config_and_loader_restored=True,
        normal_firmware_unchanged=True,independent_normal_nvme_linux_return_verified=True,linux_boot_id=boot,
        framebuffer_authority=False,physical_visibility_proven=False,visual_confirmation_required=True,compiler_calls=0,historical_archives_reverified=False,
        historical_catalog_counts=[len(context['plan']['historical_catalog']),len(context['result']['next_catalog']),len(restored['result']['next_catalog'])])

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='operation',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--baseline',type=Path,required=True)
    prep.add_argument('--prior-seal-sha256',required=True);prep.add_argument('--prior-plan-sha256',required=True);prep.add_argument('--linux-boot-id',required=True)
    pub=sub.add_parser('publish');pub.add_argument('--prepared',type=Path,required=True);pub.add_argument('--seal-sha256',required=True)
    start=sub.add_parser('launch');ret=sub.add_parser('return');restore=sub.add_parser('restore');rep=sub.add_parser('replay')
    for c in (start,ret,restore,rep):
        c.add_argument('--installation',type=Path,required=True);c.add_argument('--seal-sha256',required=True)
        c.add_argument('--plan-sha256',required=True);c.add_argument('--capture',type=Path,required=True)
    start.add_argument('--device',required=True);start.add_argument('--linux-boot-id',required=True)
    rep.add_argument('--restoration',type=Path,required=True);rep.add_argument('--restore-seal-sha256',required=True);rep.add_argument('--restore-plan-sha256',required=True)
    for c in (prep,pub,start,restore):c.add_argument('--output',type=Path,required=True)
    for c in (pub,restore):c.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if a.operation=='prepare':
        checkpoint,pin,metrics=prepare_install(a.baseline,a.prior_seal_sha256,a.prior_plan_sha256,a.linux_boot_id)
        out=local(a.output);out.mkdir(exist_ok=False);seals.save_new(out/'checkpoint.json',checkpoint,pin);save(out/'metrics.json',metrics)
        value=dict(status='prepared_only',checkpoint_sha256=pin,output=str(out),metrics=metrics)
    elif a.operation=='publish':
        folder=local(a.prepared);value=dispatch(json.loads((folder/'checkpoint.json').read_text()),a.seal_sha256,a.output,json.loads((folder/'metrics.json').read_text()),a.execute)
    elif a.operation=='restore':
        checkpoint,pin,metrics=prepare_restore(a.installation,a.seal_sha256,a.plan_sha256,a.capture)
        value=dispatch(checkpoint,pin,a.output,metrics,a.execute)
    elif a.operation=='launch':value=launch(a.installation,a.seal_sha256,a.plan_sha256,a.device,a.capture,a.output,a.linux_boot_id)
    elif a.operation=='return':
        with lease.hold(ROOT,'display-xnu-independent-return-v1'):value=transport().collect_return(load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.capture)
    else:value=replay(a.installation,a.seal_sha256,a.plan_sha256,a.capture,a.restoration,a.restore_seal_sha256,a.restore_plan_sha256)
    print(json.dumps(value,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
