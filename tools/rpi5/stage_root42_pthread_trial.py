#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Once-audited root42 publication, byte-only admission, unchanged firmware.

No board operation is implicit. Publish is explicit, one-shot and lease-bound;
an uncertain outcome preserves its transcript and is never retried here.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_trial_v3 as prior
import active_archive_loader_v2 as engine
import check_root42_pthread_package as checker
import root42_pthread_trial_core as core

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private=(getattr(prior,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private'))
GOOD=prior.GOOD['probe.bin']
PACKAGE=ROOT/'build/rpi5/root42-pthread-ulws4mq6'
MANIFEST_SHA='c45503701eaed84be939e72ddb2afb0e45af86f3d5260f1212a40eca90fcb8be'
IMAGE_SHA='cb7f1e139228be125f81adc854d11fa3607347f7046d8cb6c129801770c00d08'
CONTROLLER='root42-pthread-single-loader-v2'


def transport():
    import serial_root42_pthread_trial
    import root42_pthread_command_evidence
    import root42_pthread_evidence
    import arm_root42_pthread_reboot
    return root42_pthread_evidence


def source_pins():
    names=('stage_root42_pthread_trial.py','active_archive_loader_v2.py','tests/test_active_archive_loader_v2.py',
        'tests/test_root42_stage.py','serial_root42_pthread_trial.py','root42_pthread_command_evidence.py',
        'root42_pthread_evidence.py','arm_root42_pthread_reboot.py','tests/test_root42_pthread_transport.py',
        'root42_pthread_trial_core.py','tests/test_root42_pthread_trial.py','tests/test_root42_pthread_root.py',
        'build_root42_pthread_package.py','check_root42_pthread_package.py','tests/test_root42_pthread_package.py',
        'serial_root41_trial.py','root41_batch_evidence.py','audit_root41_trial.py',
        'capture_pcie_trace_linux_return.py','pcie_trace_evidence.py','rpi5_board_lease.py')
    return engine.source_pins()|prior.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def prepare_install(directory,prior_seal,prior_plan,boot,package=PACKAGE):
    started=time.monotonic();transport();package=local(package)
    accepted=prior.baseline(directory,prior_seal,prior_plan)
    pins=prior.merge_pins(accepted['evidence'],prior.package_graph(package,accepted['evidence']),source_pins(),prior.base.loaded_sources())
    def audit():
        if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux boot UUID required')
        if package!=PACKAGE or sha(package/'manifest.json')!=MANIFEST_SHA:raise ValueError('Exact frozen root42 package required')
        report=checker.inspect(package)
        if report['image_sha256']!=IMAGE_SHA or report['root_nodes']!=42 or report['root_files']!=30:
            raise ValueError('Exact pthread image/root geometry required')
        path,digest,size=GOOD
        publication=accepted['result']['publication'];current=publication['protected_files_sha256']
        if sha(path)!=digest or path.stat().st_size!=size or current['probe.bin']!=digest or current['bl31.bin']!=engine.original.FIRMWARE_SHA:
            raise ValueError('Known-good unchanged firmware and loader required')
        rows=accepted['result']['next_catalog'];previous=accepted['plan']['media'];binding=copy.deepcopy(previous['identity_binding'])
        if boot!=publication['identity']['boot_id']:binding['linux_boot_id_before_write']=publication['identity']['boot_id']
        binding['linux_boot_id_after_write']=boot
        if binding['linux_boot_id_before_write']==boot:raise ValueError('Distinct preceding Linux witness required')
        media=dict(host=HOST,profile=engine.TRIAL,linux_boot_id=boot,identity_binding=binding,
            protected_files=current,protected_sha256={n:r['sha256'] for n,r in publication['protected_after'].items()},nvme_backups=rows,
            old_sha256=digest,old_bytes=size,new_sha256=report['image_sha256'],new_bytes=Path(report['image']).stat().st_size,
            candidate=report['image'],preflight=report,package=str(package),source_sha256=source_pins(),controller=CONTROLLER,
            ancestry=dict(directory=accepted['directory'],checkpoint_sha256=prior_seal,plan_sha256=prior_plan,
                hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')}),
            no_firmware_change=True,no_config_change=True,no_hfs_mount=True,no_reboot=True,no_implicit_retry_or_rollback=True,
            power_loss_atomicity_claimed=False)
        engine.bound_core('0'*32).validate(media)
        if any(pins.get(n)!=h for n,h in prior.base.loaded_sources().items()):raise ValueError('Audit loaded an unsealed source dependency')
        return dict(media_plan=media,history_catalog=rows,baseline_paths=accepted['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    return checkpoint,pin,dict(full_audit_calls=1,package_compiler_audit_calls=1,historical_semantic_audit_calls=0,
        full_audit_and_seal_seconds=time.monotonic()-started,closure_files=len(checkpoint['evidence_sha256']),
        historical_archives_reverified=False,prior_catalog_count=len(accepted['result']['next_catalog']),
        archive_read_budget=engine.legacy_read_budget(accepted['result']['next_catalog']))


def sealed_operation(directory,seal_sha,plan_sha,profile):
    directory=local(directory);checkpoint=json.loads((directory/'checkpoint.json').read_text())
    payload=seals.revalidate(checkpoint,seal_sha);plan=json.loads((directory/'plan.json').read_text())
    result=json.loads((directory/'result.json').read_text())
    if plan['media']['profile']!=profile or plan['media'].get('controller')!=CONTROLLER:raise ValueError('Exact root42 operation required')
    exact,pin=engine.plan_from_seal(checkpoint,seal_sha,profile,plan['tag'],plan['media']['run'],payload['media_plan'])
    if pin!=plan_sha or not engine.same(plan,exact):raise ValueError('Retained canonical single-loader plan differs')
    engine.validate_result(result,plan,plan_sha)
    required=source_pins()
    if any(checkpoint['evidence_sha256'].get(n)!=h for n,h in required.items()):raise ValueError('Sealed root42 source closure required')
    pins=dict(checkpoint['evidence_sha256'])
    for name in ('checkpoint.json','plan.json','result.json'):pins[str(directory/name)]=sha(directory/name)
    return dict(directory=str(directory),checkpoint=checkpoint,plan=plan,result=result,evidence=pins,
        seal_sha256=seal_sha,plan_sha256=plan_sha)


def load_installation(directory,seal_sha,plan_sha):
    transport();context=sealed_operation(directory,seal_sha,plan_sha,engine.TRIAL)
    media=context['plan']['media'];publication=context['result']['publication']
    if media['new_sha256']!=IMAGE_SHA or media['package']!=str(PACKAGE):raise ValueError('Exact installed root42 package required')
    context['installed']=dict(directory=context['directory'],checkpoint_sha256=seal_sha,plan_sha256=plan_sha,
        result_sha256=sha(local(directory)/'result.json'),preflight=media['preflight'],
        loader_sha256=publication['protected_files_sha256']['probe.bin'],original_linux_boot_id=media['linux_boot_id'])
    return context


def prepare_restore(directory,seal_sha,plan_sha,capture):
    evidence=transport();started=time.monotonic();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);old=context['plan']['media'];publication=context['result']['publication']
    path,digest,size=GOOD
    if sha(path)!=digest or path.stat().st_size!=size:raise ValueError('Exact known-good restore candidate changed')
    rows=context['result']['next_catalog'];media=copy.deepcopy(old);media.pop('run')
    media.update(profile=engine.RESTORE,linux_boot_id=boot,nvme_backups=rows,candidate=str(path),
        old_sha256=old['new_sha256'],old_bytes=old['new_bytes'],new_sha256=digest,new_bytes=size,
        protected_files=publication['protected_files_sha256'],protected_sha256={n:r['sha256'] for n,r in publication['protected_after'].items()})
    media['identity_binding'].update(linux_boot_id_before_write=old['linux_boot_id'],linux_boot_id_after_write=boot)
    media['ancestry']=dict(directory=str(local(directory)),hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')},
        return_sha256=sha(local(capture)/'return.json'))
    pins=prior.merge_pins(context['evidence'],{str(local(capture)/n):sha(local(capture)/n)
        for n in ('armed.json','state.json','serial.bin','return.json')})
    def audit():
        if not engine.same(list(evidence.load_return(context,capture)),[returned,boot]):raise ValueError('Independent return changed')
        engine.bound_core('0'*32).validate(media)
        return dict(media_plan=media,history_catalog=rows,baseline_paths=context['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    return checkpoint,pin,dict(full_audit_calls=1,package_compiler_audit_calls=0,historical_semantic_audit_calls=0,
        full_audit_and_seal_seconds=time.monotonic()-started,closure_files=len(pins),historical_archives_reverified=False,
        prior_catalog_count=len(rows),archive_read_budget=engine.legacy_read_budget(rows))


def restoration(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    files=context['result']['publication']['protected_files_sha256']
    if files['probe.bin']!=GOOD[1] or files['bl31.bin']!=engine.original.FIRMWARE_SHA:
        raise ValueError('Completed known-good single-loader restoration required')
    return context


def replay(directory,seal_sha,plan_sha,capture,restored_directory,restore_seal,restore_plan):
    evidence=transport();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture)
    expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    restored=restoration(restored_directory,restore_seal,restore_plan)
    if (pin!=restore_seal or not engine.same(restored['checkpoint'],expected) or
        restored['result']['publication']['identity']['boot_id']!=boot):
        raise ValueError('Restoration does not derive from this exact trial and independent return')
    return dict(format='rpi5-root42-pthread-chain-replay-v1',publication_return_restoration_receipts_verified=True,
        capture_valid=returned['capture_valid'],diagnostic=returned.get('diagnostic'),capture_error=returned.get('capture_error'),
        independent_normal_nvme_linux_return_verified=True,returned_linux_boot_id=boot,working_loader_restored=True,
        firmware_unchanged=True,restored_loader_sha256=GOOD[1],historical_catalog_counts=[len(context['plan']['historical_catalog']),
            len(context['result']['next_catalog']),len(restored['result']['next_catalog'])],historical_archives_reverified=False,
        fresh_hardware_observation=False,compiler_calls=0,historical_semantic_audit_calls=0,networking=False,ssh_daemon=False)


def dispatch(checkpoint,seal_sha,out,metrics,execute=False):
    if execute:
        with lease.hold(ROOT,'root42-single-loader-publication-v2'):return _dispatch(checkpoint,seal_sha,out,metrics,True)
    return _dispatch(checkpoint,seal_sha,out,metrics,False)


def _dispatch(checkpoint,seal_sha,out,metrics,execute):
    payload=seals.revalidate(checkpoint,seal_sha);media=payload['media_plan']
    if media.get('controller')!=CONTROLLER or media['profile'] not in (engine.TRIAL,engine.RESTORE):raise ValueError('Root42-only reviewed operation required')
    if any(checkpoint['evidence_sha256'].get(n)!=h for n,h in source_pins().items()):raise ValueError('Complete root42 dispatch source closure required')
    if media.get('package')!=str(PACKAGE) or media['new_sha256' if media['profile']==engine.TRIAL else 'old_sha256']!=IMAGE_SHA:
        raise ValueError('Exact root42 image publication/restoration required')
    out=local(out);out.mkdir(exist_ok=False);seals.save_new(out/'checkpoint.json',checkpoint,seal_sha);save(out/'metrics.json',metrics)
    if not execute:
        save(out/'offline-plan.json',dict(checkpoint_sha256=seal_sha,media=media,hardware_admission=False))
        return dict(status='offline_only',checkpoint_sha256=seal_sha,output=str(out))
    prepare=prior.base.prior.base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-root42-v2-'")
    response=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
    work=json.loads(response.stdout)['run']
    if not re.fullmatch('/home/sandrzej/xnu-root42-v2-[a-z0-9_]{8}',work):raise ValueError('Fresh exact SSD run required')
    plan,plan_sha=engine.plan_from_seal(checkpoint,seal_sha,media['profile'],uuid.uuid4().hex,work,media);save(out/'plan.json',plan)
    subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
        media['candidate'],HOST+':'+work+'/candidate.bin'],check=True,timeout=60)
    source=engine.remote_source(checkpoint,seal_sha,plan,plan_sha);save_bytes(out/'remote-program.py',source.encode())
    save(out/'dispatch-intent.json',dict(plan_sha256=plan_sha,checkpoint_sha256=seal_sha,
        remote_source_sha256=hashlib.sha256(source.encode()).hexdigest(),run=work,one_shot=True))
    started=time.monotonic();stdout=stderr=b''
    try:
        response=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
        stdout,stderr=response.stdout,response.stderr
        for name,data in (('remote.stdout',stdout),('remote.stderr',stderr)):save_bytes(out/name,data.encode() if isinstance(data,str) else data)
        response.check_returncode();result=json.loads(stdout);engine.validate_result(result,plan,plan_sha);seals.revalidate(checkpoint,seal_sha)
        save(out/'result.json',result)
        summary=dict(status='complete',checkpoint_sha256=seal_sha,plan_sha256=plan_sha,result_sha256=sha(out/'result.json'),
            output=str(out),dispatch_seconds=time.monotonic()-started,full_audit_calls=metrics['full_audit_calls'],historical_archives_reverified=False,
            no_firmware_change=True)
        save(out/'completion.json',summary);return summary
    except BaseException as error:
        for name,data in (('remote.stdout',getattr(error,'stdout',None) or stdout),('remote.stderr',getattr(error,'stderr',None) or stderr)):
            if not (out/name).exists():
                try:save_bytes(out/name,data.encode() if isinstance(data,str) else data)
                except OSError:pass
        try:save(out/'outcome-unknown.json',dict(run=work,error=str(error) or type(error).__name__,no_retry=True,
            no_implicit_rollback=True,dispatch_intent='dispatch-intent.json'))
        except OSError:pass
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='operation',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--baseline',type=Path,required=True)
    prep.add_argument('--prior-seal-sha256',required=True);prep.add_argument('--prior-plan-sha256',required=True);prep.add_argument('--linux-boot-id',required=True)
    pub=sub.add_parser('publish');pub.add_argument('--prepared',type=Path,required=True);pub.add_argument('--seal-sha256',required=True)
    restore=sub.add_parser('restore');restore.add_argument('--installation',type=Path,required=True);restore.add_argument('--seal-sha256',required=True)
    restore.add_argument('--plan-sha256',required=True);restore.add_argument('--capture',type=Path,required=True)
    replay_=sub.add_parser('replay');replay_.add_argument('--installation',type=Path,required=True);replay_.add_argument('--seal-sha256',required=True)
    replay_.add_argument('--plan-sha256',required=True);replay_.add_argument('--capture',type=Path,required=True)
    replay_.add_argument('--restoration',type=Path,required=True);replay_.add_argument('--restore-seal-sha256',required=True)
    replay_.add_argument('--restore-plan-sha256',required=True)
    for child in (prep,pub,restore):child.add_argument('--output',type=Path,required=True)
    for child in (pub,restore):child.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if a.operation=='replay':
        value=replay(a.installation,a.seal_sha256,a.plan_sha256,a.capture,a.restoration,a.restore_seal_sha256,a.restore_plan_sha256)
    elif a.operation=='prepare':
        checkpoint,pin,metrics=prepare_install(a.baseline,a.prior_seal_sha256,a.prior_plan_sha256,a.linux_boot_id)
        out=local(a.output);out.mkdir(exist_ok=False);seals.save_new(out/'checkpoint.json',checkpoint,pin);save(out/'metrics.json',metrics)
        value=dict(status='prepared_only',checkpoint_sha256=pin,output=str(out),metrics=metrics)
    elif a.operation=='publish':
        prepared=local(a.prepared);checkpoint=json.loads((prepared/'checkpoint.json').read_text());metrics=json.loads((prepared/'metrics.json').read_text())
        value=dispatch(checkpoint,a.seal_sha256,a.output,metrics,a.execute)
    else:
        checkpoint,pin,metrics=prepare_restore(a.installation,a.seal_sha256,a.plan_sha256,a.capture)
        value=dispatch(checkpoint,pin,a.output,metrics,a.execute)
    print(json.dumps(value,indent=2,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
