# SPDX-License-Identifier: BSD-2-Clause
"""Single-loader active archive publisher; firmware never changes.

The original actual-file-tested single-image engine retains all identity,
mount, current-file, raw-snapshot, journal, and fresh rollback guards. Only
selected known-good archive bytes are rechecked; history remains metadata.
No device access occurs at import, plan construction, or receipt validation.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import types
try:
    from . import root96_media_core as original
    from . import active_archive_pair_v2 as shared
    from . import trial_checkpoint_v2 as seals
except ImportError:
    import root96_media_core as original
    import active_archive_pair_v2 as shared
    import trial_checkpoint_v2 as seals

SOURCE=Path(original.__file__).resolve()
SOURCE_SHA='990ddfd1f9f641933afce5edb0dc3bd5b2d4cd2a176b15fc921940086d49ff11'
SHARED_SHA='57ff757e7ea22285b31552a7375b1242c82ad3831b3a67d12e515cdf3250e255'
TRIAL='active-archive-loader-trial-v2'
RESTORE='active-archive-loader-restore-v2'
FORMAT='rpi5-active-archive-loader-plan-v2'
RESULT='rpi5-active-archive-loader-result-v2'
HELPERS=shared.HELPERS
catalog=shared.catalog
same=shared.same
select_baseline=shared.select_baseline
legacy_read_budget=shared.legacy_read_budget


def bound_core(tag):
    if not isinstance(tag,str) or not re.fullmatch('[0-9a-f]{32}',tag):raise ValueError('Fresh exact trial tag required')
    text=getattr(original,'_active_window_source',None)
    if text is None:text=SOURCE.read_text()
    if hashlib.sha256(text.encode()).hexdigest()!=SOURCE_SHA:raise ValueError('Frozen single-image publisher changed')
    for old,new,count in (("'root96-install-v1'",repr(TRIAL),3),("'root96-restore-v1'",repr(RESTORE),3),
        ("nvme_backups_verified=plan['nvme_backups']","active_baseline_archives_verified=plan['nvme_backups']",1),
        ("(work/'result.json')","(work/'publication.json')",1)):
        if text.count(old)!=count:raise ValueError('Single-image derivation boundary changed: '+old)
        text=text.replace(old,new)
    module=types.ModuleType('_active_archive_loader_v2');exec(compile(text,str(SOURCE),'exec'),module.__dict__)
    checked=module.validate
    def validate(plan):
        if plan.get('profile') not in (TRIAL,RESTORE):raise ValueError('Single-loader install or restore only; reclaim disabled')
        if original.REDUNDANT in plan['protected_files']:raise ValueError('Unexpected redundant SD file')
        return checked(plan)
    module.validate=module.validate_files=validate
    module.TEMP={TRIAL:'probe.loader-'+tag+'.tmp',RESTORE:'probe.loader-return-'+tag+'.tmp'}
    return module


def source_pins():
    pins=shared.source_pins()
    if pins.get(str(Path(shared.__file__).resolve()))!=SHARED_SHA:raise ValueError('Frozen common archive policy changed')
    pins.update({str(SOURCE):SOURCE_SHA,str(Path(__file__).resolve()):seals.sha(Path(__file__).resolve())})
    seals.check_pins(pins)
    return pins


# Reuse exactly the reviewed typed plan/closure policy with a private global
# namespace. No original module, pair policy, or function globals are mutated.
def _scoped(function):
    return types.FunctionType(function.__code__,globals(),argdefs=function.__defaults__)


plan_from_seal=_scoped(shared.plan_from_seal)
validate_plan=_scoped(shared.validate_plan)


def remote_source(checkpoint,checkpoint_sha,plan,expected_plan_sha):
    payload=checkpoint['payload']
    fresh,pin=plan_from_seal(checkpoint,checkpoint_sha,plan['media']['profile'],plan['tag'],plan['media']['run'],payload['media_plan'])
    if not same(plan,fresh) or pin!=expected_plan_sha:raise ValueError('Remote dispatch differs from sealed single-loader plan')
    modules=[(name,SOURCE.parent/file) for name,file in zip(('capture','helper','snapshots','reference','guarded'),HELPERS)]
    modules += [('pcie_trace_pair_core',Path(shared.original.__file__).resolve()),
        ('trial_checkpoint_v2',Path(seals.__file__).resolve()),('active_archive_pair_v2',Path(shared.__file__).resolve()),
        ('root96_media_core',SOURCE),('active_archive_loader_v2',Path(__file__).resolve())]
    code='import types,sys,json\n'
    for name,path in modules:
        text=path.read_text()
        if hashlib.sha256(text.encode()).hexdigest()!=checkpoint['evidence_sha256'].get(str(path)):
            raise ValueError('Dispatched source differs from sealed closure')
        code+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\n'
        code+=f'{name}.__file__={str(path)!r}\n{name}._active_window_source={text!r}\nexec({text!r},{name}.__dict__)\n'
    code+='PLAN=json.loads('+repr(json.dumps(plan))+')\n'
    code+='print(json.dumps(active_archive_loader_v2.execute(PLAN,'+repr(expected_plan_sha)+',capture,helper,snapshots,reference,guarded)))\n'
    compile(code,'<single-loader-remote>','exec')
    return code


def _new_rows(plan,backups):
    p=plan['media']
    return [dict(path=p['run']+'/'+r['saved_as'],bytes=r['bytes'],sha256=r['sha256']) for r in backups]+[
        dict(path=p['run']+'/previous.bin',bytes=p['old_bytes'],sha256=p['old_sha256'])]


def _result(plan,pin,publication):
    rows=plan['historical_catalog'];new=_new_rows(plan,publication['backups']);combined=rows+new;catalog(combined)
    return dict(format=RESULT,status='complete',plan_sha256=pin,checkpoint_sha256=plan['checkpoint_sha256'],publication=publication,
        historical_catalog=rows,historical_catalog_sha256=plan['historical_catalog_sha256'],historical_archives_reverified=False,
        active_baseline_archives_verified=plan['media']['nvme_backups'],newly_created_rollback_archives_verified=new,
        next_catalog=combined,next_catalog_sha256=seals.digest(combined),preserved_archive_count=len(rows),created_archive_count=4,
        deleted_archives=[],no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)


def execute(plan,expected_plan_sha,capture,helper,snapshots,reference,guarded,run=None):
    if seals.digest(plan)!=expected_plan_sha:raise ValueError('Exact dispatched plan changed')
    validate_plan(plan)
    publication=bound_core(plan['tag']).execute(plan['media'],capture,helper,snapshots,reference,guarded,run)
    result=_result(plan,expected_plan_sha,publication);validate_result(result,plan,expected_plan_sha)
    path=Path(plan['media']['run'])/'result.json'
    with path.open('x') as out:json.dump(result,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return result


def validate_result(result,plan,expected_plan_sha):
    validate_plan(plan)
    if seals.digest(plan)!=expected_plan_sha:raise ValueError('Publication plan digest differs')
    p=plan['media'];expected=dict(p['protected_files']);expected['probe.bin']=p['new_sha256']
    extents=(('mbr','/dev/mmcblk0',512,'mbr.before-write.bin'),
        ('boot','/dev/mmcblk0p1',536870912,'boot-partition.before-write.img'),
        ('hfs','/dev/mmcblk0p2',134217728,'hfs-partition.before.img'))
    backups=[dict(device=node,bytes=size,sha256=p['protected_sha256'][kind],saved_as=name) for kind,node,size,name in extents]
    publication=result.get('publication',{});post=publication.get('protected_after',{})
    if set(post)!={'mbr','boot','hfs'}:raise ValueError('Three complete post-publication extents required')
    for kind,node,size,_ in extents:
        r=post[kind]
        if (set(r)!={'device','bytes','sha256','saved_as'} or r['device']!=node or type(r['bytes']) is not int or
            r['bytes']!=size or r['saved_as'] is not None or not isinstance(r['sha256'],str) or
            not re.fullmatch('[0-9a-f]{64}',r['sha256']) or (kind!='boot' and r['sha256']!=p['protected_sha256'][kind])):
            raise ValueError('Post-publication extent or protected MBR/HFS differs')
    exact=dict(status='complete',profile=p['profile'],run=p['run'],
        identity=dict(identity=p['identity_binding']['expected'],boot_id=p['linux_boot_id'],hostname='kamidana'),
        backups=backups,protected_after=post,protected_files_sha256=expected,active_baseline_archives_verified=p['nvme_backups'],
        archived_file='probe.bin',previous_file_sha256=p['old_sha256'],previous_file_bytes=p['old_bytes'],previous_file_name='previous.bin',
        deleted_files=[],replaced_files=['probe.bin'],retained_sd_backup=original.RETAINED,retained_sd_backup_sha256=original.GOOD_SHA,
        firmware_sha256=original.FIRMWARE_SHA,boot_unmounted=True,no_config_change=True,no_firmware_change=True,no_hfs_mount=True,
        no_reboot=True,power_loss_atomicity_claimed=False,no_implicit_retry_or_rollback=True)
    if not same(publication,exact):raise ValueError('Typed single-loader publication receipt differs')
    if not same(result,_result(plan,expected_plan_sha,exact)):raise ValueError('Typed single-loader archive receipt differs')
    return dict(typed_receipt_matches=True,historical_archives_reverified=False,new_hardware_read_performed=False,
        old_archive_payloads_read=0,firmware_changed=False)
