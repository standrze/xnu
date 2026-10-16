#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One fixed CPU-owned ring trial, three guarded SD targets and zero UART TX.

Typed completed PID1 restoration is the only intake. Package/source/report
audited once; staging/recording/replay is byte-only. Unknown publication or
reboot outcomes are never retried. All three originals are explicitly restored.
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
import stage_restart_late_trial as preceding
import stage_display_compact_trial as previous_compact
import stage_display_query_trial as observer
import stage_link_trial_v2 as publisher
import gem_cpu_batch_media_v1 as engine
import gem_cpu_batch_case_v1 as case
from tools.rpi5 import check_gem_dma_batch_trial as checker
from tools.rpi5 import gem_dma_batch_serial as protocol
from tools.rpi5 import gem_dma_batch_contract as contracts
from tools.rpi5 import prepare_display_xnu_trial_v2 as graph
prior=preceding
ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private=(getattr(preceding,n) for n in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private'))
CONTROLLER='gem-cpu-batch-three-target-controller-v1'
PACKAGE=case.PACKAGE
MANIFEST_SHA=case.MANIFEST_SHA
IMAGE_SHA=case.IMAGE_SHA
TAG=case.TAG
REPORT=case.REPORT
REPORT_SHA=case.REPORT_SHA
CONFIG=ROOT/'build/rpi5/display-allocate-config32-20261013/config.txt'
DESCRIPTOR='gem-cpu-batch-fixed52'
GOOD={'config.txt':(ROOT/'build/rpi5/gate2-config.txt',engine.ORIGINAL_CONFIG_SHA,len(engine.ORIGINAL_CONFIG)),
      'bl31.bin':publisher.GOOD['bl31.bin'],'probe.bin':publisher.GOOD['probe.bin']}
merge_pins=preceding.prior.merge_pins
# The exact compiler-directory metadata exception remains pinned. Rebind only
# the selected manifest/profile owner; never normalize arbitrary include paths.
_graph_scope=dict(vars(graph),stage=sys.modules[__name__])
_graph_scope['include_directory']=types.FunctionType(graph.include_directory.__code__,_graph_scope)
package_graph=types.FunctionType(graph.package_graph.__code__,_graph_scope)


def transport():
    import serial_gem_cpu_batch_trial_v1
    import gem_cpu_batch_evidence_v1
    import arm_gem_cpu_batch_reboot_v1
    return gem_cpu_batch_evidence_v1

def source_pins():
    names=('stage_gem_cpu_batch_trial_v1.py','serial_gem_cpu_batch_trial_v1.py',
        'gem_cpu_batch_evidence_v1.py','arm_gem_cpu_batch_reboot_v1.py',
        'gem_cpu_batch_media_v1.py','gem_cpu_batch_case_v1.py',
        'tests/test_gem_cpu_batch_media_v1.py','tests/test_gem_cpu_batch_transport_v1.py',
        'tests/test_gem_cpu_batch_latest_intake_v1.py',
        'build_gem_dma_batch_trial.py','check_gem_dma_batch_trial.py','qualify_gem_dma_batch_trial.py',
        'gem_dma_batch_serial.py','gem_dma_batch_contract.py')
    if case.FROZEN is not True:raise ValueError('CPU-batch package/report case is not frozen')
    return preceding.source_pins()|engine.source_pins()|qualification_pins()|{
        str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{
        str(CONFIG):engine.TRIAL_CONFIG_SHA,str(GOOD['config.txt'][0]):engine.ORIGINAL_CONFIG_SHA,
        str(REPORT):REPORT_SHA,str(case.QUALIFICATION):case.QUALIFICATION_SHA}

def qualification_pins():
    """Inventory exact current receipt bytes, never replay compiler/history.

    The sole initial checker semantically validates these receipts. Later
    sealing/admission compares only their separately retained byte closure.
    """
    if case.FROZEN is not True or sha(case.QUALIFICATION)!=case.QUALIFICATION_SHA:
        raise ValueError('Exact final-package stack qualification required')
    q=json.loads(Path(case.QUALIFICATION).read_bytes())
    documents=[Path(case.QUALIFICATION),Path(q['early_audit']),Path(q['rp1_measurements']),Path(q['measurements'])]
    pins={}
    def walk(v):
        if isinstance(v,dict):
            for key,value in v.items():walk(key);walk(value)
        elif isinstance(v,list):
            for value in v:walk(value)
        elif isinstance(v,str) and v.startswith('/'):
            path=Path(v)
            if '..' in path.parts:raise ValueError('Noncanonical qualification reference')
            if path.is_file() and path.is_relative_to(ROOT):pins[str(path)]=sha(path)
    for path in documents:
        pins[str(path)]=sha(path);walk(json.loads(path.read_bytes()))
    return pins


def valid_report(report):
    if case.FROZEN is not True or sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):
        raise ValueError('Exact separately retained CPU-batch report required')
    expected=dict(profile=checker.b.PROFILE,package=str(PACKAGE),manifest_sha256=MANIFEST_SHA,
        image_sha256=IMAGE_SHA,image_bytes=engine.IMAGE_BYTES,firmware_sha256=case.FIRMWARE_SHA,
        tag=TAG,marker=checker.b.profile.marker(TAG),trial_marker=checker.b.profile.marker(TAG),
        bootargs=checker.b.profile.BOOTARGS,cpu_ring_contract=contracts.contract(),
        inherited_capability_contracts=contracts.inherited(),cpu_owned_only=True,
        dma_reachability_qualified=False,queue_publication=False,hardware_execution=False,
        kernel_live_stack_audit_required=False,early_kernel_stack_audit_required=False,
        software_trial_qualified=True,physical_execution_proven=False,
        qualification=str(case.QUALIFICATION),qualification_sha256=case.QUALIFICATION_SHA)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()):
        raise ValueError('Exact52-row retained CPU-only qualified image required')
    stack=report.get('target_stack',{})
    if (stack.get('target_stack_receipts_bound') is not True or stack.get('whole_kernel_stack_proven') is not False or
        stack.get('compiler_replayed') is not False or stack.get('hardware_executed') is not False):
        raise ValueError('Exact finite target-stack receipts required')
    return True


def baseline(directory,seal_sha,plan_sha):
    accepted=preceding.restoration(directory,seal_sha,plan_sha)
    files=accepted['result']['publication']['protected_files_sha256']
    if any(files.get(n)!=v[1] for n,v in GOOD.items()):
        raise ValueError('Completed typed late-PID1/restart original config/normal firmware/zsh restoration required')
    return accepted


def admit(checkpoint):
    import serial_gem_cpu_batch_trial_v1 as recorder
    media=checkpoint['payload']['media_plan'];valid_report(media['preflight'])
    engine.bound_core('0'*32).validate_files(media)
    context={'descriptor':get_descriptor(DESCRIPTOR),'installed':{
        'directory':str(ROOT/'build/rpi5/prepublication-only-no-installation'),'preflight':media['preflight']},
        'evidence':checkpoint['evidence_sha256']}
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_gem_cpu_batch_trial_v1.py' or
        bound.__globals__['protocol'] is not protocol or
        bound.__globals__['assert_modem_ready'] is not recorder.assert_modem_ready or
        Path(recorder.stage.__file__).resolve()!=Path(__file__).resolve()):
        raise ValueError('Exact new zero-TX recorder namespace and pre-ARM modem gate required')
    return dict(actual_report_bound=True,actual_recorder_source_members=len(sources),
        recorder_namespace_bound_without_serial=True,modem_gate_bound_before_arm=True,
        transmitted_bytes=0,physical_execution_proven=False,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,boot):
    start=time.monotonic();transport()
    if case.FROZEN is not True:raise ValueError('Unsealed case cannot prepare publication')
    accepted=baseline(directory,prior_seal,prior_plan)
    if CONFIG.read_bytes()!=engine.TRIAL_CONFIG or GOOD['config.txt'][0].read_bytes()!=engine.ORIGINAL_CONFIG:
        raise ValueError('Exact retained original and derived config32 bytes required')
    pins=merge_pins(accepted['evidence'],package_graph(PACKAGE,accepted['evidence']),
        source_pins(),publisher.loaded_sources())
    def audit():
        if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux UUID required')
        if sha(PACKAGE/'manifest.json')!=MANIFEST_SHA:raise ValueError('Exact frozen allocation package required')
        report=checker.inspect(PACKAGE,MANIFEST_SHA,case.QUALIFICATION,case.QUALIFICATION_SHA);valid_report(report)
        publication=accepted['result']['publication'];current=dict(publication['protected_files_sha256'])
        rows=accepted['result']['next_catalog'];binding=copy.deepcopy(accepted['plan']['media']['identity_binding'])
        if boot!=publication['identity']['boot_id']:binding['linux_boot_id_before_write']=publication['identity']['boot_id']
        binding['linux_boot_id_after_write']=boot
        if binding['linux_boot_id_before_write']==boot:raise ValueError('Distinct preceding Linux witness required')
        files=[];candidates={}
        new={'config.txt':(CONFIG,engine.TRIAL_CONFIG_SHA,len(engine.TRIAL_CONFIG)),
             'bl31.bin':(case.FIRMWARE,case.FIRMWARE_SHA,case.FIRMWARE_BYTES),
             'probe.bin':(PACKAGE/'probe.bin',IMAGE_SHA,engine.IMAGE_BYTES)}
        for name,(path,digest,size) in GOOD.items():
            if sha(path)!=digest or path.stat().st_size!=size or current.pop(name)!=digest:raise ValueError('Original config/loader changed')
            target,h,n=new[name];files.append(dict(target=name,candidate='candidate-'+name,
                old_sha256=digest,old_bytes=size,new_sha256=h,new_bytes=n));candidates[name]=str(target)
        media=dict(host=HOST,profile=engine.TRIAL,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
            protected_files=current,protected_sha256={n:r['sha256'] for n,r in publication['protected_after'].items()},
            nvme_backups=rows,descriptor=DESCRIPTOR,preflight=report,package=str(PACKAGE),
            source_sha256=source_pins(),controller=CONTROLLER,
            ancestry=dict(directory=accepted['directory'],checkpoint_sha256=prior_seal,plan_sha256=prior_plan,
                hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')}),
            explicit_firmware_change=True,exact_temporary_config32=True,three_target_publication=True,no_hfs_mount=True,no_reboot=True,
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
    # Compatibility pair view is ONLY firmware+loader identifiers required by
    # the unchanged zero-TX recorder; triple_sha256 records the full operation.
    context['installed']=dict(directory=context['directory'],checkpoint_sha256=seal_sha,plan_sha256=plan_sha,
        result_sha256=sha(local(directory)/'result.json'),preflight=media['preflight'],loader_sha256=IMAGE_SHA,
        config_sha256=engine.TRIAL_CONFIG_SHA,original_linux_boot_id=media['linux_boot_id'],
        triple_sha256=context['result']['publication']['triple_sha256'],
        pair_sha256={n:context['result']['publication']['triple_sha256'][n] for n in ('bl31.bin','probe.bin')})
    context['descriptor']=get_descriptor(DESCRIPTOR)
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
    pins=merge_pins(context['evidence'],{str(local(capture)/n):sha(local(capture)/n)
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
    if kind!=DESCRIPTOR or case.FROZEN is not True:raise ValueError('Fixed frozen CPU-batch case required')
    return {'hardware_allowed':True,'protocol':protocol,'record':dict(package=str(PACKAGE),
        package_manifest_sha256=MANIFEST_SHA,marker=checker.b.profile.marker(TAG),firmware_sha256=case.FIRMWARE_SHA)}

_dispatch=private(publisher.dispatch,engine=engine,descriptors=types.SimpleNamespace(get=get_descriptor),subprocess=upload_transport)


def dispatch(checkpoint,seal_sha,out,metrics,execute=False):
    media=seals.revalidate(checkpoint,seal_sha)['media_plan']
    if media.get('controller')!=CONTROLLER:raise ValueError('Exact config-loader controller required')
    admit(checkpoint)
    with lease.hold(ROOT,'gem-cpu-batch-three-target-v1') if execute else __import__('contextlib').nullcontext():
        return _dispatch(checkpoint,seal_sha,out,metrics,execute)

def launch(directory,seal_sha,plan_sha,device,capture,output,boot):
    import arm_gem_cpu_batch_reboot_v1 as launcher
    return launcher.launch(directory,seal_sha,plan_sha,device,capture,output,boot)


def replay(directory,seal_sha,plan_sha,capture,restored_directory,restore_seal,restore_plan):
    evidence=transport();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    restored=restoration(restored_directory,restore_seal,restore_plan)
    if pin!=restore_seal or not engine.same(restored['checkpoint'],expected) or restored['result']['publication']['identity']['boot_id']!=boot:
        raise ValueError('Restoration not derived from exact allocation trial and Linux return')
    return dict(format='rpi5-gem-cpu-batch-three-target-chain-v1',capture_valid=returned['capture_valid'],
        diagnostic=returned['diagnostic'],capture_error=returned['capture_error'],original_config_firmware_and_loader_restored=True,
        normal_firmware_restored=True,independent_normal_nvme_linux_return_verified=True,linux_boot_id=boot,
        framebuffer_authority=False,physical_visibility_proven=False,visual_confirmation_required=False,compiler_calls=0,historical_archives_reverified=False,
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
        with lease.hold(ROOT,'gem-cpu-batch-independent-return-v1'):value=transport().collect_return(load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.capture)
    else:value=replay(a.installation,a.seal_sha256,a.plan_sha256,a.capture,a.restoration,a.restore_seal_sha256,a.restore_plan_sha256)
    print(json.dumps(value,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())

