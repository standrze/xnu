#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Concrete next-link pair: one full audit, sealed byte checks, active rollback.

Hardware dispatch is explicit, lease-bound and never retried. The old AXI
descriptor exists solely for offline tests and cannot dispatch a publication.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import active_archive_pair_v2 as engine
import trial_checkpoint_v2 as seals
import stage_pcie_axi_trial as prior
import serial_root96_trial as history
import rpi5_board_lease as lease
import link_trial_descriptor_v2 as descriptors

ROOT,HOST,SSH=prior.ROOT,prior.HOST,prior.SSH
sha=seals.sha
GOOD={'bl31.bin':(prior.OLD_FIRMWARE,engine.GOOD_FW_SHA,engine.GOOD_FW_BYTES),
      'probe.bin':(ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin',engine.original.GOOD_ZSH_SHA,engine.original.GOOD_ZSH_BYTES)}
FORMAT='rpi5-next-link-controller-v2'


def save(path,value):
    save_bytes(path,seals.canonical(value)+b'\n')


def save_bytes(path,data):
    with Path(path).open('xb') as out:
        out.write(data);out.flush();os.fsync(out.fileno())
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def local(path):
    path=Path(path).resolve()
    if path.parent!=ROOT/'build/rpi5':raise ValueError('Exact local evidence child required')
    return path


def source_pins():
    paths=[Path(__file__).resolve(),Path(descriptors.__file__).resolve(),Path(lease.__file__).resolve(),
        Path(prior.__file__).resolve(),Path(history.__file__).resolve()]
    paths.extend(ROOT/'tools/rpi5'/name for name in
        ('serial_link_trial_v2.py','link_trial_evidence_v2.py','tests/test_link_trial_frontend_v2.py',
         'arm_pcie_trace_reboot.py','tests/test_active_archive_pair_v2.py',
         'serial_pcie_trace_trial.py','pcie_trace_evidence.py','capture_pcie_trace_linux_return.py'))
    return engine.source_pins()|{str(p):sha(p) for p in paths}


def loaded_sources():
    result={}
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT) and path.is_file():result[str(path)]=sha(path)
    return result


def load_descriptor(kind):
    # Import all recorder/return/launcher code BEFORE collecting the audit
    # closure. A newly added protocol is not necessarily a loader input pin.
    import serial_link_trial_v2
    import link_trial_evidence_v2
    import arm_pcie_trace_reboot
    return descriptors.get(kind)


def closure(baseline,package):
    """Seal all local receipt/package dependencies, never remote archive payloads.

    Historical expected hashes are not silently reinterpreted as current proof:
    the one full auditor still validates their semantics. This collects the
    actual bytes that auditor observes, including archived source snapshots.
    """
    pins=source_pins()|history.receipt_evidence_pins(local(baseline))
    pending=[local(baseline)/'plan.json',local(baseline)/'result.json',Path(package).resolve()/'manifest.json']
    pending.extend(Path(name) for name in pins if name.endswith('.json'))
    seen=set()
    def add(name):
        if not isinstance(name,str) or not name.startswith('/'):return
        path=Path(name)
        if '..' in path.parts or name.startswith('/home/'):return
        if path.is_dir() and path.is_relative_to(ROOT/'build/rpi5'):
            candidate=path/'manifest.json'
            if candidate.is_file():pending.append(candidate)
        elif path.is_file():
            pins[str(path)]=sha(path)
            if path.suffix=='.json':pending.append(path)
    def walk(value):
        if isinstance(value,dict):
            for name,item in value.items():add(name);walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,str):add(value)
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        if len(seen)>2000:raise ValueError('Bounded manifest/receipt graph exceeded')
        pins[str(path)]=sha(path)
        raw=path.read_text();decoder=json.JSONDecoder();offset=0
        # Some retained compiler/recorder reports contain multiple JSON
        # documents. Pin and traverse every document, not just the first row.
        while raw[offset:].strip():
            offset+=len(raw[offset:])-len(raw[offset:].lstrip())
            # Clang -MJ writes a compilation-database fragment with its final
            # comma. It is not a missing or ignored dependency document.
            if offset and raw[offset:]==',\n':break
            if offset and raw[offset:].strip()==',':break
            try:value,end=decoder.raw_decode(raw,offset)
            except json.JSONDecodeError as error:raise ValueError('Unparseable dependency report: '+str(path)) from error
            walk(value);offset=end
    for path,_,_ in GOOD.values():pins[str(path)]=sha(path)
    # Capture loaded verifier/helper code as well as serialized package inputs.
    pins.update(loaded_sources())
    seals.check_pins(pins)
    return pins


def baseline_paths(rows):
    selected={}
    for name,(_,digest,size) in GOOD.items():
        matches=[r['path'] for r in rows if r['sha256']==digest and r['bytes']==size]
        if not matches:raise ValueError('Previously accepted known-good SSD pair missing from catalog')
        selected[name]=matches[0]
    engine.select_baseline(rows,selected)
    return selected


def full_install_audit(baseline,package,boot,kind):
    """The sole semantic package/128-ancestor audit for this installation."""
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux boot UUID required')
    descriptor=descriptors.get(kind);baseline=local(baseline);package=local(package)
    if sha(package/'manifest.json')!=descriptor['manifest_sha256']:raise ValueError('Exact frozen descriptor package required')
    old=json.loads((baseline/'plan.json').read_text());result=json.loads((baseline/'result.json').read_text())
    prior.validate_result(result,old)
    if old['profile']!=prior.RESTORE:raise ValueError('Completed actual AXI pair restore required')
    rows=prior.inherited(old,result,128)
    report=descriptor['checker'].inspect(package)
    if not report['marker'].startswith(descriptor['marker_prefix']):raise ValueError('Exact descriptor marker required')
    if report['firmware_sha256']!='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b':
        raise ValueError('Unchanged accepted secure verifier firmware required')
    current=result['protected_files_sha256'];files=[];candidates={}
    new={'bl31.bin':(Path(report['firmware']),report['firmware_sha256']),
         'probe.bin':(Path(report['image']),report['image_sha256'])}
    for name,(path,digest,size) in GOOD.items():
        if sha(path)!=digest or path.stat().st_size!=size or current[name]!=digest:raise ValueError('Original normal pair changed')
        target,target_sha=new[name];candidates[name]=str(target)
        files.append(dict(target=name,candidate='candidate-'+name,old_sha256=digest,new_sha256=target_sha,
            old_bytes=size,new_bytes=target.stat().st_size))
    binding=copy.deepcopy(old['identity_binding'])
    if boot!=result['identity']['boot_id']:binding['linux_boot_id_before_write']=result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot
    if binding['linux_boot_id_before_write']==boot:raise ValueError('Missing distinct Linux witness')
    media=dict(host=HOST,profile=engine.TRIAL,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
        protected_files={n:h for n,h in current.items() if n not in GOOD},
        protected_sha256={n:r['sha256'] for n,r in result['protected_after'].items()},nvme_backups=rows,
        descriptor=kind,preflight=report,package=str(package),source_sha256=source_pins(),
        ancestry=dict(directory=str(baseline),hashes={n:sha(baseline/n) for n in ('plan.json','result.json')}),
        no_hfs_mount=True,no_config_change=True,no_reboot=True,explicit_firmware_change=True,
        no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
    engine.bound_core('0'*32).validate_files(media)
    return dict(media_plan=media,history_catalog=rows,baseline_paths=baseline_paths(rows))


def prepare_install(baseline,package,boot,kind='link'):
    started=time.monotonic();descriptor=load_descriptor(kind);pins=closure(baseline,package)
    pins.update({str(p):sha(p) for p in descriptor.get('additional_sources',[])})
    def complete_audit():
        result=full_install_audit(baseline,package,boot,kind)
        if any(pins.get(name)!=digest for name,digest in loaded_sources().items()):
            raise ValueError('Full audit loaded an unsealed source dependency')
        return result
    checkpoint,digest=seals.create(complete_audit,pins)
    return checkpoint,digest,dict(full_audit_calls=1,full_audit_and_seal_seconds=time.monotonic()-started,
        closure_files=len(checkpoint['evidence_sha256']),historical_archives_reverified=False,
        archive_read_budget=engine.legacy_read_budget(checkpoint['payload']['history_catalog']))


def load_installation(directory,seal_sha,plan_sha):
    directory=local(directory);checkpoint=json.loads((directory/'checkpoint.json').read_text())
    payload=seals.revalidate(checkpoint,seal_sha)
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    if plan['media']['profile']!=engine.TRIAL:raise ValueError('Installed next-link trial required')
    exact,exact_sha=engine.plan_from_seal(checkpoint,seal_sha,engine.TRIAL,plan['tag'],plan['media']['run'],payload['media_plan'])
    if not engine.same(plan,exact) or exact_sha!=plan_sha:raise ValueError('Retained installation plan digest differs')
    engine.validate_result(result,plan,plan_sha)
    descriptor=load_descriptor(plan['media']['descriptor'])
    required=source_pins()|loaded_sources()
    required.update({str(p):sha(p) for p in descriptor.get('additional_sources',[])})
    if any(checkpoint['evidence_sha256'].get(name)!=digest for name,digest in required.items()):
        raise ValueError('Complete recorder/checker/protocol source closure required')
    evidence=dict(checkpoint['evidence_sha256'])
    for name in ('checkpoint.json','plan.json','result.json'):evidence[str(directory/name)]=sha(directory/name)
    installed=dict(directory=str(directory),checkpoint_sha256=seal_sha,plan_sha256=plan_sha,
        result_sha256=sha(directory/'result.json'),preflight=plan['media']['preflight'],
        pair_sha256=result['publication']['pair_sha256'],original_linux_boot_id=plan['media']['linux_boot_id'])
    return dict(plan=plan,result=result,checkpoint=checkpoint,installed=installed,descriptor=descriptor,evidence=evidence)


def dispatch(checkpoint,seal_sha,out,metrics,execute=False):
    """Exact publication once. Any uncertain dispatch stays uncertain, never retried."""
    payload=seals.revalidate(checkpoint,seal_sha);media=payload['media_plan'];descriptor=descriptors.get(media['descriptor'])
    if execute and not descriptor['hardware_allowed']:raise ValueError('Offline descriptor cannot dispatch hardware')
    out=local(out);out.mkdir(exist_ok=False)
    seals.save_new(out/'checkpoint.json',checkpoint,seal_sha);save(out/'metrics.json',metrics)
    if not execute:
        save(out/'offline-plan.json',dict(checkpoint_sha256=seal_sha,media=media,hardware_admission=False))
        return dict(status='offline_only',checkpoint_sha256=seal_sha,output=str(out))
    prepare=prior.base.prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'","prefix='xnu-link-v2-'")
    response=subprocess.run(SSH+['python3 -'],input=prepare,text=True,capture_output=True,check=True,timeout=30)
    work=json.loads(response.stdout)['run']
    if not re.fullmatch('/home/sandrzej/xnu-link-v2-[a-z0-9_]{8}',work):raise ValueError('Fresh exact SSD run required')
    plan,plan_sha=engine.plan_from_seal(checkpoint,seal_sha,media['profile'],uuid.uuid4().hex,work,media)
    save(out/'plan.json',plan)
    for row in media['files']:
        subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
            media['candidates'][row['target']],HOST+':'+work+'/'+row['candidate']],check=True,timeout=60)
    source=engine.remote_source(checkpoint,seal_sha,plan,plan_sha)
    save_bytes(out/'remote-program.py',source.encode())
    save(out/'dispatch-intent.json',dict(plan_sha256=plan_sha,checkpoint_sha256=seal_sha,
        remote_source_sha256=hashlib.sha256(source.encode()).hexdigest(),run=work,one_shot=True))
    started=time.monotonic()
    stdout=stderr=b''
    try:
        response=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
        stdout,stderr=response.stdout,response.stderr
        for name,data in (('remote.stdout',stdout),('remote.stderr',stderr)):
            save_bytes(out/name,data.encode() if isinstance(data,str) else data)
        response.check_returncode()
        result=json.loads(stdout);engine.validate_result(result,plan,plan_sha);seals.revalidate(checkpoint,seal_sha)
        save(out/'result.json',result)
        summary=dict(status='complete',checkpoint_sha256=seal_sha,plan_sha256=plan_sha,result_sha256=sha(out/'result.json'),
            output=str(out),dispatch_seconds=time.monotonic()-started,full_audit_calls=metrics['full_audit_calls'],
            historical_archives_reverified=False)
        save(out/'completion.json',summary)
    except BaseException as error:
        # Even successful publication becomes outcome-unknown if local receipt
        # persistence or validation fails. Never overwrite a partial receipt.
        for name,data in (('remote.stdout',getattr(error,'stdout',None) or stdout),
                          ('remote.stderr',getattr(error,'stderr',None) or stderr)):
            if not (out/name).exists():
                try:save_bytes(out/name,data.encode() if isinstance(data,str) else data)
                except OSError:pass  # Preserve dispatch intent even if disk is unavailable.
        try:save(out/'outcome-unknown.json',dict(run=work,error=str(error) or type(error).__name__,
            no_retry=True,no_implicit_rollback=True,dispatch_intent='dispatch-intent.json'))
        except OSError:pass  # Never hide the original error or overwrite unknown.
        raise
    return summary


def prepare_restore(installation,seal_sha,plan_sha,capture):
    import link_trial_evidence_v2 as evidence
    started=time.monotonic();context=load_installation(installation,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture)
    old=context['plan']['media'];publication=context['result']['publication']
    rows=context['result']['next_catalog']
    if len(rows)!=133:raise ValueError('Exact first v2 link installation catalog required')
    media=copy.deepcopy(old);media.pop('run');media.update(profile=engine.RESTORE,linux_boot_id=boot,nvme_backups=rows)
    media['identity_binding'].update(linux_boot_id_before_write=old['linux_boot_id'],linux_boot_id_after_write=boot)
    media['files']=[];media['candidates']={};protected=dict(publication['protected_files_sha256'])
    for row in old['files']:
        name=row['target'];path,digest,size=GOOD[name]
        if protected.pop(name)!=row['new_sha256'] or sha(path)!=digest or path.stat().st_size!=size:
            raise ValueError('Exact installed/current and original restore pair required')
        media['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=row['new_sha256'],
            old_bytes=row['new_bytes'],new_sha256=digest,new_bytes=size))
        media['candidates'][name]=str(path)
    media['protected_files']=protected
    media['protected_sha256']={n:r['sha256'] for n,r in publication['protected_after'].items()}
    media['ancestry']=dict(directory=str(local(installation)),hashes={n:sha(local(installation)/n)
        for n in ('checkpoint.json','plan.json','result.json')},return_sha256=sha(local(capture)/'return.json'))
    pins=dict(context['evidence']);pins.update({str(local(capture)/n):sha(local(capture)/n)
        for n in ('armed.json','state.json','serial.bin','receive-events.jsonl','return.json')})
    def complete_return_audit():
        if evidence.load_return(context,capture)!=(returned,boot):raise ValueError('Exact independent return changed')
        return dict(media_plan=media,history_catalog=rows,baseline_paths=context['checkpoint']['payload']['baseline_paths'])
    checkpoint,digest=seals.create(complete_return_audit,pins)
    return checkpoint,digest,dict(full_audit_calls=1,package_compiler_audit_calls=0,historical_ancestry_replays=0,
        full_audit_and_seal_seconds=time.monotonic()-started,closure_files=len(pins),historical_archives_reverified=False,
        archive_read_budget=engine.legacy_read_budget(rows))


def launch(installation,seal_sha,plan_sha,device,capture,output,boot):
    import arm_pcie_trace_reboot as arm
    import serial_link_trial_v2 as recorder
    context=load_installation(installation,seal_sha,plan_sha);installed=context['installed']
    if not context['descriptor']['hardware_allowed']:raise ValueError('Offline descriptor cannot launch hardware')
    if boot!=installed['original_linux_boot_id']:raise ValueError('Exact staged Linux boot required')
    capture=local(capture);output=local(output)
    if capture.exists():raise ValueError('Fresh capture directory required')
    command=[sys.executable,str(Path(recorder.__file__).resolve()),device,str(capture),
        '--installation',installed['directory'],'--seal-sha256',seal_sha,'--plan-sha256',plan_sha,'--seconds','600']
    expected='RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+installed['pair_sha256']['probe.bin']+' FIRMWARE_SHA='+installed['pair_sha256']['bl31.bin']
    def armed(pid):
        recorder.revalidate(context)
        value=json.loads((capture/'armed.json').read_text())
        if (value.get('pid')!=pid or value.get('installation')!=installed or value.get('transmitted_bytes')!=0 or
            value.get('device')!=device or value.get('baud')!=115200 or (capture/'state.json').exists() or
            value.get('source_sha256')!=recorder.bound_sources(context) or
            value.get('receipt_evidence_sha256')!=context['evidence']):raise ValueError('Exact sealed armed child required')
        return dict(pid=pid,armed_sha256=sha(capture/'armed.json'),installation=installed,capture=str(capture))
    source=arm.reboot_source(boot,context['plan']['media']['identity_binding']['expected']['root'].split())
    def reboot():
        save(output/'reboot-source.json',dict(source=source,sha256=hashlib.sha256(source.encode()).hexdigest()))
        try:
            r=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=30)
            out,err,rc,timed_out=r.stdout,r.stderr,r.returncode,False
        except subprocess.TimeoutExpired as error:
            out,err,rc,timed_out=error.stdout or b'',error.stderr or b'',None,True
        for name,data in (('reboot.stdout',out),('reboot.stderr',err)):
            with (output/name).open('xb') as target:target.write(data.encode() if isinstance(data,str) else data)
        if isinstance(out,bytes):out=out.decode(errors='replace')
        return dict(returncode=rc,timed_out=timed_out,verification_marker_observed=out.count('VERIFIED_SSD_LINUX_REBOOT_ONCE ')==1,
            reboot_outcome='unknown_until_capture_and_independent_linux_return',no_retry=True,
            stdout_sha256=sha(output/'reboot.stdout'),stderr_sha256=sha(output/'reboot.stderr'))
    # The child holds the OS board lease throughout arming/capture. Parent never
    # acquires a second exclusive lock that could deadlock the same workflow.
    return arm.arm_once(output,command,expected,armed,reboot)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='operation',required=True)
    install=sub.add_parser('install');install.add_argument('--baseline',type=Path,required=True)
    install.add_argument('--package',type=Path,required=True);install.add_argument('--linux-boot-id',required=True)
    restore=sub.add_parser('restore');start=sub.add_parser('launch');returned=sub.add_parser('return')
    publish=sub.add_parser('publish');publish.add_argument('--prepared',type=Path,required=True)
    publish.add_argument('--seal-sha256',required=True)
    for child in (restore,start,returned):
        child.add_argument('--installation',type=Path,required=True);child.add_argument('--seal-sha256',required=True)
        child.add_argument('--plan-sha256',required=True);child.add_argument('--capture',type=Path,required=True)
    start.add_argument('--device',required=True);start.add_argument('--linux-boot-id',required=True)
    for child in (install,restore,start,publish):child.add_argument('--output',type=Path,required=True)
    for child in (install,restore,publish):child.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if a.operation=='launch':
        value=launch(a.installation,a.seal_sha256,a.plan_sha256,a.device,a.capture,a.output,a.linux_boot_id)
    elif a.operation=='return':
        import link_trial_evidence_v2 as evidence
        with lease.hold(ROOT,'next-link-read-only-return-v2'):
            value=evidence.collect_return(load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.capture)
    else:
        with lease.hold(ROOT,'next-link-active-window-publication-v2'):
            if a.operation=='publish':
                prepared=local(a.prepared);checkpoint=json.loads((prepared/'checkpoint.json').read_text())
                pin=a.seal_sha256;seals.revalidate(checkpoint,pin)
                metrics=json.loads((prepared/'metrics.json').read_text())
            elif a.operation=='install':checkpoint,pin,metrics=prepare_install(a.baseline,a.package,a.linux_boot_id)
            else:checkpoint,pin,metrics=prepare_restore(a.installation,a.seal_sha256,a.plan_sha256,a.capture)
            value=dispatch(checkpoint,pin,a.output,metrics,a.execute)
    print(json.dumps(value,sort_keys=True))


if __name__=='__main__':main()
