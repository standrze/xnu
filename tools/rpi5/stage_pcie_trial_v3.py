#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Reusable reviewed-case controller: typed prior restore, one new package audit.

Uses the unchanged v2 active-archive publisher and zero-input transport. Case
data are immutable hash-bound JSON; historical counts are derived, never guessed.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import time
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_link_trial_v2 as base
import pcie_trial_descriptor_v3 as descriptors

ROOT,HOST,SSH,GOOD,engine,seals,lease,sha,save,save_bytes,local=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','GOOD','engine','seals','lease','sha','save','save_bytes','local'))
FROZEN={
    'stage_link_trial_v2.py':'74b9245fdc7176869f1f472d9793596998609fdd023fd447b7a13a0cea359547',
    'serial_link_trial_v2.py':'ebd1bfd0cd372841a77a64a75a4a425be515993016d45bf4e6c509917abd2588',
    'link_trial_evidence_v2.py':'c880a3b99c3269d0c77003ca7bb2fbe1064c1c89d8342df6e2e157a35e5928fd'}


def private(fn,**bindings):
    return types.FunctionType(fn.__code__,dict(fn.__globals__,**bindings),argdefs=fn.__defaults__)


def source_pins():
    fixed={str(ROOT/'tools/rpi5'/n):h for n,h in FROZEN.items()};seals.check_pins(fixed)
    names=('stage_pcie_trial_v3.py','pcie_trial_descriptor_v3.py','serial_pcie_trial_v3.py',
        'pcie_trial_evidence_v3.py','tests/test_pcie_trial_v3.py')
    return base.source_pins()|fixed|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


def load_descriptor(reference):
    import serial_pcie_trial_v3
    import pcie_trial_evidence_v3
    import arm_pcie_trace_reboot
    return descriptors.get(reference)


def sealed_operation(directory,seal_sha,plan_sha,profile):
    """Typed prior-v2/v3 intake. No old checker, recursion, compiler or SSH."""
    directory=local(directory);checkpoint=json.loads((directory/'checkpoint.json').read_text())
    payload=seals.revalidate(checkpoint,seal_sha)
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    if plan['media']['profile']!=profile:raise ValueError('Exact typed operation required')
    exact,pin=engine.plan_from_seal(checkpoint,seal_sha,profile,plan['tag'],plan['media']['run'],payload['media_plan'])
    if pin!=plan_sha or not engine.same(plan,exact):raise ValueError('Retained canonical operation plan differs')
    engine.validate_result(result,plan,plan_sha)
    pins=dict(checkpoint['evidence_sha256'])
    for name in ('checkpoint.json','plan.json','result.json'):pins[str(directory/name)]=sha(directory/name)
    return dict(directory=str(directory),checkpoint=checkpoint,plan=plan,result=result,evidence=pins,
        seal_sha256=seal_sha,plan_sha256=plan_sha)


def baseline(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.RESTORE)
    if context['result']['publication']['pair_sha256']!={n:v[1] for n,v in GOOD.items()}:
        raise ValueError('Completed original firmware and zsh restoration required')
    return context


def merge_pins(*maps):
    result={}
    for rows in maps:
        for name,pin in rows.items():
            if name in result and result[name]!=pin:raise ValueError('Previously sealed evidence drift: '+name)
            result[name]=pin
    return result


def package_graph(package,prior_pins):
    """Extend a validated closed graph; never walk old manifests recursively.

    Prior bytes are still all checked by the seal. Their dependency edges were
    already audited and cannot change without invalidating that prior seal.
    Each genuinely new file/document is hashed/traversed at most once here.
    """
    pins=dict(prior_pins);pending=[];seen=set()
    def add(name):
        if not isinstance(name,str) or not name.startswith('/') or name in pins or name.startswith('/home/'):return
        path=Path(name)
        if '..' in path.parts:raise ValueError('Noncanonical dependency path')
        if path.is_dir() and path.is_relative_to(ROOT/'build/rpi5'):
            manifest=path/'manifest.json'
            if manifest.is_file():add(str(manifest))
        elif path.is_file():
            pins[name]=sha(path)
            if path.suffix=='.json':pending.append(path)
    def walk(value):
        if isinstance(value,dict):
            for name,item in value.items():add(name);walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,str):add(value)
    add(str(package/'manifest.json'))
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        if len(seen)>2000:raise ValueError('New package document graph exceeded bound')
        raw=path.read_text();offset=0;decoder=json.JSONDecoder()
        while raw[offset:].strip():
            offset+=len(raw[offset:])-len(raw[offset:].lstrip())
            if offset and raw[offset:].strip()==',':break
            try:value,end=decoder.raw_decode(raw,offset)
            except json.JSONDecodeError as error:raise ValueError('Unparseable new dependency report: '+str(path)) from error
            walk(value);offset=end
    return pins


def prepare_install(directory,prior_seal,prior_plan,descriptor_reference,boot):
    start=time.monotonic();descriptor=load_descriptor(descriptor_reference)
    prior=baseline(directory,prior_seal,prior_plan);record=descriptor['record'];package=Path(record['package'])
    graph=package_graph(package,prior['evidence'])
    pins=merge_pins(prior['evidence'],graph,source_pins(),base.loaded_sources(),record['source_sha256'],
        {descriptor_reference['path']:descriptor_reference['sha256']})
    def audit():
        if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot):raise ValueError('Fresh Linux boot UUID required')
        if sha(package/'manifest.json')!=record['package_manifest_sha256']:raise ValueError('Exact reviewed immutable package required')
        report=descriptor['checker'].inspect(package)
        if report['marker']!=record['marker'] or report['firmware_sha256']!=record['firmware_sha256']:
            raise ValueError('Checker output differs from reviewed case marker/firmware')
        rows=prior['result']['next_catalog'];publication=prior['result']['publication'];previous=prior['plan']['media']
        binding=copy.deepcopy(previous['identity_binding'])
        if boot!=publication['identity']['boot_id']:binding['linux_boot_id_before_write']=publication['identity']['boot_id']
        binding['linux_boot_id_after_write']=boot
        if binding['linux_boot_id_before_write']==boot:raise ValueError('Distinct preceding Linux witness required')
        current=publication['protected_files_sha256'];files=[];candidates={}
        new={'bl31.bin':(Path(report['firmware']),report['firmware_sha256']),
            'probe.bin':(Path(report['image']),report['image_sha256'])}
        for name,(path,digest,size) in GOOD.items():
            if sha(path)!=digest or path.stat().st_size!=size or current[name]!=digest:raise ValueError('Known-good original pair changed')
            target,target_sha=new[name];candidates[name]=str(target)
            files.append(dict(target=name,candidate='candidate-'+name,old_sha256=digest,old_bytes=size,
                new_sha256=target_sha,new_bytes=target.stat().st_size))
        media=dict(host=HOST,profile=engine.TRIAL,linux_boot_id=boot,identity_binding=binding,files=files,candidates=candidates,
            protected_files={n:h for n,h in current.items() if n not in GOOD},
            protected_sha256={n:r['sha256'] for n,r in publication['protected_after'].items()},nvme_backups=rows,
            descriptor=descriptor_reference,preflight=report,package=str(package),source_sha256=source_pins(),
            controller='reviewed-case-active-window-v3',
            ancestry=dict(directory=prior['directory'],hashes={n:sha(Path(prior['directory'])/n) for n in ('checkpoint.json','plan.json','result.json')},
                checkpoint_sha256=prior_seal,plan_sha256=prior_plan),
            no_hfs_mount=True,no_config_change=True,no_reboot=True,explicit_firmware_change=True,
            no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
        engine.bound_core('0'*32).validate_files(media)
        if any(pins.get(n)!=h for n,h in base.loaded_sources().items()):raise ValueError('Package audit loaded an unsealed source')
        return dict(media_plan=media,history_catalog=rows,baseline_paths=prior['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    return checkpoint,pin,dict(full_audit_calls=1,package_compiler_audit_calls=1,historical_semantic_audit_calls=0,
        full_audit_and_seal_seconds=time.monotonic()-start,closure_files=len(checkpoint['evidence_sha256']),
        historical_archives_reverified=False,prior_catalog_count=len(prior['result']['next_catalog']),
        archive_read_budget=engine.legacy_read_budget(prior['result']['next_catalog']))


def load_installation(directory,seal_sha,plan_sha):
    context=sealed_operation(directory,seal_sha,plan_sha,engine.TRIAL)
    if context['plan']['media'].get('controller')!='reviewed-case-active-window-v3':raise ValueError('Installed v3 case required')
    descriptor=load_descriptor(context['plan']['media']['descriptor'])
    required=source_pins()|base.loaded_sources()|descriptor['record']['source_sha256']
    if any(context['evidence'].get(n)!=h for n,h in required.items()):raise ValueError('Sealed v3 transport/descriptor closure required')
    context.update(descriptor=descriptor,installed=dict(directory=context['directory'],checkpoint_sha256=seal_sha,plan_sha256=plan_sha,
        result_sha256=sha(Path(context['directory'])/'result.json'),preflight=context['plan']['media']['preflight'],
        pair_sha256=context['result']['publication']['pair_sha256'],original_linux_boot_id=context['plan']['media']['linux_boot_id']))
    return context


def prepare_restore(directory,seal_sha,plan_sha,capture):
    import pcie_trial_evidence_v3 as evidence
    start=time.monotonic();context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture);old=context['plan']['media'];publication=context['result']['publication']
    rows=context['result']['next_catalog'];media=copy.deepcopy(old);media.pop('run')
    media.update(profile=engine.RESTORE,linux_boot_id=boot,nvme_backups=rows)
    media['identity_binding'].update(linux_boot_id_before_write=old['linux_boot_id'],linux_boot_id_after_write=boot)
    media['files']=[];media['candidates']={};protected=dict(publication['protected_files_sha256'])
    for row in old['files']:
        name=row['target'];path,digest,size=GOOD[name]
        if protected.pop(name)!=row['new_sha256'] or sha(path)!=digest or path.stat().st_size!=size:raise ValueError('Exact installed/current and original pair required')
        media['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=row['new_sha256'],old_bytes=row['new_bytes'],new_sha256=digest,new_bytes=size))
        media['candidates'][name]=str(path)
    media['protected_files']=protected;media['protected_sha256']={n:r['sha256'] for n,r in publication['protected_after'].items()}
    media['ancestry']=dict(directory=str(local(directory)),hashes={n:sha(local(directory)/n) for n in ('checkpoint.json','plan.json','result.json')},return_sha256=sha(local(capture)/'return.json'))
    pins=merge_pins(context['evidence'],{str(local(capture)/n):sha(local(capture)/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl','return.json')})
    def audit():
        if not engine.same(list(evidence.load_return(context,capture)),[returned,boot]):raise ValueError('Independent return changed')
        return dict(media_plan=media,history_catalog=rows,baseline_paths=context['checkpoint']['payload']['baseline_paths'])
    checkpoint,pin=seals.create(audit,pins)
    return checkpoint,pin,dict(full_audit_calls=1,package_compiler_audit_calls=0,historical_semantic_audit_calls=0,
        full_audit_and_seal_seconds=time.monotonic()-start,closure_files=len(pins),historical_archives_reverified=False,
        prior_catalog_count=len(rows),archive_read_budget=engine.legacy_read_budget(rows))


dispatch=private(base.dispatch,descriptors=descriptors)


def launch(directory,seal_sha,plan_sha,device,capture,output,boot):
    # The frozen one-shot launch body imports the old recorder by name; its
    # module is replaced only in this private function's import operation.
    import serial_pcie_trial_v3 as recorder
    import builtins
    def import_(name,*args,**kw):
        if name=='serial_link_trial_v2':return recorder
        return builtins.__import__(name,*args,**kw)
    scoped=dict(vars(builtins),__import__=import_)
    return private(base.launch,load_installation=load_installation,__builtins__=scoped)(directory,seal_sha,plan_sha,device,capture,output,boot)


def replay(directory,seal_sha,plan_sha,capture,restoration,restore_seal,restore_plan):
    import pcie_trial_evidence_v3 as evidence
    context=load_installation(directory,seal_sha,plan_sha)
    returned,boot=evidence.load_return(context,capture)
    expected,pin,_=prepare_restore(directory,seal_sha,plan_sha,capture)
    if pin!=restore_seal:raise ValueError('Restoration is not derived from this exact trial and independent return')
    restored=baseline(restoration,restore_seal,restore_plan)
    if not engine.same(restored['checkpoint'],expected) or restored['result']['publication']['identity']['boot_id']!=boot:
        raise ValueError('Explicit restored original pair/boot differs')
    diagnostic=returned['diagnostic'];counts=[len(context['plan']['historical_catalog']),len(context['result']['next_catalog']),len(restored['result']['next_catalog'])]
    return dict(format='rpi5-reviewed-case-v3-chain-replay',publication_return_restoration_receipts_verified=True,
        descriptor=context['plan']['media']['descriptor'],capture_valid=returned['capture_valid'],diagnostic=diagnostic,
        capture_error=returned['capture_error'],rp1_id_trial_pass=bool(diagnostic and diagnostic.get('rp1_id_trial_pass') is True),
        independent_normal_nvme_linux_return_verified=True,returned_linux_boot_id=boot,working_firmware_and_zsh_restored=True,
        restored_pair_sha256=restored['result']['publication']['pair_sha256'],historical_catalog_counts=counts,
        historical_archives_reverified=False,fresh_hardware_observation=False,ethernet_proven=False,
        compiler_calls=0,historical_semantic_audit_calls=0,zero_serial_tx=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='operation',required=True)
    prepare=sub.add_parser('prepare');prepare.add_argument('--baseline',type=Path,required=True)
    prepare.add_argument('--prior-seal-sha256',required=True);prepare.add_argument('--prior-plan-sha256',required=True)
    prepare.add_argument('--descriptor',type=Path,required=True);prepare.add_argument('--descriptor-sha256',required=True)
    prepare.add_argument('--linux-boot-id',required=True)
    publish=sub.add_parser('publish');publish.add_argument('--prepared',type=Path,required=True);publish.add_argument('--seal-sha256',required=True)
    start=sub.add_parser('launch');returned=sub.add_parser('return');restore=sub.add_parser('restore');audit=sub.add_parser('replay')
    for child in (start,returned,restore,audit):
        child.add_argument('--installation',type=Path,required=True);child.add_argument('--seal-sha256',required=True)
        child.add_argument('--plan-sha256',required=True);child.add_argument('--capture',type=Path,required=True)
    start.add_argument('--device',required=True);start.add_argument('--linux-boot-id',required=True)
    audit.add_argument('--restoration',type=Path,required=True);audit.add_argument('--restore-seal-sha256',required=True);audit.add_argument('--restore-plan-sha256',required=True)
    for child in (prepare,publish,start,restore):child.add_argument('--output',type=Path,required=True)
    for child in (publish,restore):child.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if a.operation=='replay':value=replay(a.installation,a.seal_sha256,a.plan_sha256,a.capture,a.restoration,a.restore_seal_sha256,a.restore_plan_sha256)
    elif a.operation=='launch':value=launch(a.installation,a.seal_sha256,a.plan_sha256,a.device,a.capture,a.output,a.linux_boot_id)
    elif a.operation=='return':
        import pcie_trial_evidence_v3 as evidence
        with lease.hold(ROOT,'reviewed-case-read-only-return-v3'):value=evidence.collect_return(load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.capture)
    else:
        with lease.hold(ROOT,'reviewed-case-active-window-v3'):
            if a.operation=='prepare':
                reference={'path':str(a.descriptor.resolve()),'sha256':a.descriptor_sha256}
                checkpoint,pin,metrics=prepare_install(a.baseline,a.prior_seal_sha256,a.prior_plan_sha256,reference,a.linux_boot_id)
                out=local(a.output);out.mkdir(exist_ok=False);seals.save_new(out/'checkpoint.json',checkpoint,pin);save(out/'metrics.json',metrics)
                value=dict(status='prepared_only',output=str(out),checkpoint_sha256=pin,metrics=metrics)
            else:
                if a.operation=='publish':
                    prepared=local(a.prepared);checkpoint=json.loads((prepared/'checkpoint.json').read_text());pin=a.seal_sha256
                    seals.revalidate(checkpoint,pin);metrics=json.loads((prepared/'metrics.json').read_text())
                else:checkpoint,pin,metrics=prepare_restore(a.installation,a.seal_sha256,a.plan_sha256,a.capture)
                value=dispatch(checkpoint,pin,a.output,metrics,a.execute)
    print(json.dumps(value,sort_keys=True))


if __name__=='__main__':main()
