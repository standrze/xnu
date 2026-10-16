# SPDX-License-Identifier: BSD-2-Clause
"""Exact config32/loader pair engine; normal firmware remains protected.

The source-pinned actual-file-tested pair publisher retains its exact card,
root, raw snapshot, mount, copy/readback and durable journal safeguards. Its
only replacement targets here are config.txt and probe.bin, in that order.
Both old files are SSD-archived and both new temps verified before any rename.
Configuration is the literal original plus one32-bit line under sole[all].
The reverse transition restores both originals. No automatic rollback, retry,
power-loss atomicity, firmware modification or historical-payload rehash claim.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import types
try:
    from . import pcie_trace_pair_core as original
    from . import trial_checkpoint_v2 as seals
except ImportError:
    import pcie_trace_pair_core as original
    import trial_checkpoint_v2 as seals

SOURCE=Path(original.__file__).resolve()
SOURCE_SHA='59228462f1a6d0cc81bbba7645a9196e9ec01731b7893db933b8eb2a5900dd76'
HELPERS={
    'hfs_persistence_capture_core.py':'daf6a09b48574251130014ac1fe9d8cac1e9046a4b17c5e0c78ce7bcbcefaf95',
    'probe_install_core.py':'e510e4f3d3fb8a6591f8c9bc95b06532e29b823461d3b06ed25720705350d599',
    'write_trial_backups.py':'327a0552d015928bcebd82f7993147969a9d7794890aa336ebf94d070cd3e265',
    'pcie_recovery_reference_core.py':'af58b12827265399c68fdba96c559f1c12ebd14136249f4930e74e8495ce7b9a',
    'recovery_trial_install_core.py':'686a1a8007dec83be286a4be5cae8beebf3285f8b57b861c8ba2cc3f9a8e7788'}
TRIAL='display-compact-config-loader-trial-v1'
RESTORE='display-compact-config-loader-restore-v1'
FORMAT='rpi5-display-compact-config-loader-plan-v1'
RESULT='rpi5-display-compact-config-loader-result-v1'
GOOD_FW_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
GOOD_FW_BYTES=45174
ORIGINAL_CONFIG="[all]\narm_64bit=1\nenable_uart=1\nuart_2ndstage=1\nauto_initramfs=0\ncamera_auto_detect=0\ndisplay_auto_detect=0\narmstub=bl31.bin\nkernel=probe.bin\nkernel_address=0x9000000\ndevice_tree=bcm2712-rpi-5-b.dtb\ndevice_tree_address=0xb000000\nset_reboot_order=0xf6\nkernel_watchdog_timeout=60\n".encode('ascii')
ORIGINAL_CONFIG_SHA='aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28'
TRIAL_CONFIG=ORIGINAL_CONFIG+b'framebuffer_depth=32\n'
TRIAL_CONFIG_SHA=hashlib.sha256(TRIAL_CONFIG).hexdigest()
IMAGE_SHA='1b22884d149cd8c334b81fb6b29136f81f070cc197a26315d5e46cab57e6fe63'
IMAGE_BYTES=75200



def catalog(rows):
    if not isinstance(rows,list) or not 2<=len(rows)<=10000:raise ValueError('Bounded historical catalog required')
    paths=set()
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'path','bytes','sha256'} or
            not isinstance(row['path'],str) or not Path(row['path']).is_absolute() or '..' in Path(row['path']).parts or
            type(row['bytes']) is not int or not 0<row['bytes']<=1024*1024*1024 or
            not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']) or row['path'] in paths):
            raise ValueError('Exact unique archive rows required')
        paths.add(row['path'])
    return {r['path']:r for r in rows}


def select_baseline(rows,selected):
    by_path=catalog(rows)
    if not isinstance(selected,dict) or set(selected)!={'bl31.bin','probe.bin'} or not all(isinstance(v,str) for v in selected.values()):
        raise ValueError('Explicit two-file rollback baseline required')
    expected={'bl31.bin':(GOOD_FW_SHA,GOOD_FW_BYTES),'probe.bin':(original.GOOD_ZSH_SHA,original.GOOD_ZSH_BYTES)}
    result=[]
    for name in original.TARGETS:
        row=by_path.get(selected[name]);sha,size=expected[name]
        if not row or (row['sha256'],row['bytes'])!=(sha,size):raise ValueError('Known-good baseline catalog binding differs')
        result.append(copy.deepcopy(row))
    return result


def bound_core(tag):
    if not isinstance(tag,str) or not re.fullmatch('[0-9a-f]{32}',tag):raise ValueError('Fresh exact trial tag required')
    text=getattr(original,'_active_window_source',None)
    if text is None:text=SOURCE.read_text()
    if hashlib.sha256(text.encode()).hexdigest()!=SOURCE_SHA:raise ValueError('Frozen actual-file-tested publisher changed')
    for old,new in (("'pcie-trace-pair-trial-v1'",repr(TRIAL)),("'pcie-trace-pair-restore-v1'",repr(RESTORE))):
        if text.count(old)!=2:raise ValueError('Publisher profile binding changed')
        text=text.replace(old,new)
    # Result semantics deliberately differ: only the selected baseline rows
    # were rehashed; do not falsely retain the old whole-chain field name.
    for old,new in (("nvme_backups_verified=plan['nvme_backups']","active_baseline_archives_verified=plan['nvme_backups']"),
                    ("(work/'result.json')","(work/'publication.json')")):
        if text.count(old)!=1:raise ValueError('Publisher receipt boundary changed')
        text=text.replace(old,new)
    # A separately named canonical config+loader publisher. No old engine or
    # no-config-change assertion is patched at runtime outside this derivation.
    for old,new,count in (("'bl31.bin'","'config.txt'",3),
        ("no_config_change=True","config_changed=True",1),
        ("firmware_changed=True","firmware_changed=False",1)):
        if text.count(old)!=count:raise ValueError('Config-loader derivation boundary changed: '+old)
        text=text.replace(old,new)
    module=types.ModuleType('_display_compact_media_v1');exec(compile(text,str(SOURCE),'exec'),module.__dict__)
    module.NAMES={
        TRIAL:{'config.txt':('config.pre-displaycompact-'+tag+'.txt','config.displaycompact-'+tag+'.tmp','config-before.txt'),
               'probe.bin':(original.REUSED_ZSH_BACKUP,'probe.displaycompact-'+tag+'.tmp','loader-before.bin')},
        RESTORE:{'config.txt':('config.displaycompact-trial-'+tag+'.txt','config.displaycompact-return-'+tag+'.tmp','config-trial.txt'),
                 'probe.bin':(None,'probe.displaycompact-return-'+tag+'.tmp','loader-trial.bin')}}
    checked=module.validate_files
    def validate_files(plan):
        checked(plan)
        if (plan.get('protected_files',{}).get('bl31.bin')!=GOOD_FW_SHA or
            'config.txt' in plan['protected_files'] or 'probe.bin' in plan['protected_files']):
            raise ValueError('Normal firmware protected and exact two replacement targets required')
        if hashlib.sha256(ORIGINAL_CONFIG).hexdigest()!=ORIGINAL_CONFIG_SHA or ORIGINAL_CONFIG.count(b'[all]\n')!=1 or b'framebuffer_' in ORIGINAL_CONFIG:
            raise ValueError('Exact unambiguous original config required')
        old,new=(ORIGINAL_CONFIG,TRIAL_CONFIG) if plan['profile']==TRIAL else (TRIAL_CONFIG,ORIGINAL_CONFIG)
        cfg=plan['files'][0];image=plan['files'][1]
        if (cfg['old_sha256']!=hashlib.sha256(old).hexdigest() or cfg['new_sha256']!=hashlib.sha256(new).hexdigest() or
            cfg['old_bytes']!=len(old) or cfg['new_bytes']!=len(new)):
            raise ValueError('Exact original/derived32 config transition required')
        old_sha,new_sha,old_size,new_size=(original.GOOD_ZSH_SHA,IMAGE_SHA,original.GOOD_ZSH_BYTES,IMAGE_BYTES) if plan['profile']==TRIAL else (IMAGE_SHA,original.GOOD_ZSH_SHA,IMAGE_BYTES,original.GOOD_ZSH_BYTES)
        if (image['old_sha256'],image['new_sha256'],image['old_bytes'],image['new_bytes'])!=(old_sha,new_sha,old_size,new_size):
            raise ValueError('Exact allocation/working loader transition required')
    module.validate_files=validate_files
    return module

def plan_from_seal(seal,seal_sha,operation,tag,run,base_plan):
    """No recursive package audit: fresh byte closure plus exact current state.

    The full-audit payload contains media_plan (without run), history_catalog,
    and baseline_paths, produced by the new controller's initial full auditor.
    That auditor must bind the actual new package, desired operation, fresh boot
    and prior protected state. This function cannot turn an old result into a
    different operation, package or boot: base_plan must match it byte-for-byte.
    """
    data=seals.revalidate(seal,seal_sha)
    for name,digest in source_pins().items():
        if seal['evidence_sha256'].get(name)!=digest:raise ValueError('Complete media engine source closure required in seal')
    if set(data)!={'media_plan','history_catalog','baseline_paths'} or not same(data['media_plan'],base_plan):
        raise ValueError('Typed sealed full-audit media plan differs')
    if 'run' in base_plan or base_plan.get('profile')!=operation or operation not in (TRIAL,RESTORE):
        raise ValueError('Exact planned operation without prior run required')
    core=bound_core(tag);core.validate_files(base_plan)
    if not isinstance(run,str) or not Path(run).is_absolute() or '..' in Path(run).parts:
        raise ValueError('Explicit fresh absolute SSD work path required')
    rows=copy.deepcopy(data['history_catalog']);active=select_baseline(rows,data['baseline_paths'])
    if not same(base_plan.get('nvme_backups'),rows):raise ValueError('Full auditor must retain exact historical catalog')
    inner=copy.deepcopy(base_plan);inner.update(run=run,nvme_backups=active)
    result=dict(format=FORMAT,checkpoint_sha256=seal_sha,tag=tag,media=inner,
        historical_catalog=rows,historical_catalog_sha256=seals.digest(rows),
        historical_archives_reverified=False,selected_baseline_paths=data['baseline_paths'],
        publisher_source_sha256=SOURCE_SHA,no_history_deletion=True,no_implicit_retry_or_rollback=True)
    validate_plan(result)
    return result,seals.digest(result)


def source_pins():
    pins={str(SOURCE):SOURCE_SHA}
    for name,digest in HELPERS.items():pins[str(SOURCE.parent/name)]=digest
    for p in (Path(__file__).resolve(),Path(seals.__file__).resolve()):pins[str(p)]=seals.sha(p)
    seals.check_pins(pins)
    return pins


def remote_source(checkpoint,checkpoint_sha,plan,expected_plan_sha):
    """Generate but never send a fixed source-pinned remote invocation.

    Revalidation is byte-only; full auditors are not invoked here. A future
    stager must reserve a fresh SSD run and upload only the two exact candidates
    before this invocation, recording an outcome-unknown receipt on disconnect.
    """
    # plan_from_seal performs the single complete byte-only revalidation below.
    payload=checkpoint['payload']
    fresh,fresh_sha=plan_from_seal(checkpoint,checkpoint_sha,plan['media']['profile'],
        plan['tag'],plan['media']['run'],payload['media_plan'])
    if not same(plan,fresh) or expected_plan_sha!=fresh_sha:raise ValueError('Remote dispatch differs from byte-sealed plan')
    names=('capture','helper','snapshots','reference','guarded')
    modules=[(name,SOURCE.parent/file) for name,file in zip(names,HELPERS)]
    modules += [('pcie_trace_pair_core',SOURCE),('trial_checkpoint_v2',Path(seals.__file__).resolve()),
                ('display_compact_media_v1',Path(__file__).resolve())]
    code='import types,sys,json\n'
    for name,path in modules:
        text=path.read_text()
        if hashlib.sha256(text.encode()).hexdigest()!=checkpoint['evidence_sha256'].get(str(path)):
            raise ValueError('Dispatched engine source differs from sealed closure')
        code+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\n'
        code+=f'{name}.__file__={str(path)!r}\n{name}.__package__=""\n{name}._active_window_source={text!r}\n'
        code+=f'exec({text!r},{name}.__dict__)\n'
    code+='PLAN=json.loads('+repr(json.dumps(plan))+')\n'
    code+='print(json.dumps(display_compact_media_v1.execute(PLAN,'+repr(expected_plan_sha)+',capture,helper,snapshots,reference,guarded)))\n'
    # Catch construction errors locally, without executing any target operation.
    compile(code,'<active-archive-v2-remote>','exec')
    return code


def validate_plan(plan):
    if (set(plan)!={'format','checkpoint_sha256','tag','media','historical_catalog','historical_catalog_sha256',
            'historical_archives_reverified','selected_baseline_paths','publisher_source_sha256',
            'no_history_deletion','no_implicit_retry_or_rollback'} or plan['format']!=FORMAT or
        plan['publisher_source_sha256']!=SOURCE_SHA or plan['historical_archives_reverified'] is not False or
        plan['no_history_deletion'] is not True or plan['no_implicit_retry_or_rollback'] is not True or
        not re.fullmatch('[0-9a-f]{64}',plan['checkpoint_sha256'])):
        raise ValueError('Exact v2 active-archive plan schema required')
    rows=plan['historical_catalog'];active=select_baseline(rows,plan['selected_baseline_paths'])
    if plan['historical_catalog_sha256']!=seals.digest(rows) or not same(plan['media']['nvme_backups'],active):
        raise ValueError('Active/historical archive boundary differs')
    if any(Path(r['path']).parent==Path(plan['media']['run']) for r in rows):
        raise ValueError('Prior artifacts cannot occupy fresh operation run')
    bound_core(plan['tag']).validate_files(plan['media'])


def execute(plan,expected_plan_sha,capture,helper,snapshots,reference,guarded,run=None):
    """Remote entry after controller byte revalidation; no SSH/reboot here.

    Expected plan digest comes from the controller's just-created sealed plan,
    not from an untrusted file on the target. Existing work/journals still refuse
    unknown retry. A partial pair may remain after failure; nothing rolls back.
    """
    if seals.digest(plan)!=expected_plan_sha:raise ValueError('Exact dispatched plan changed')
    validate_plan(plan);core=bound_core(plan['tag'])
    publication=core.execute(plan['media'],capture,helper,snapshots,reference,guarded,run)
    if not same(publication['active_baseline_archives_verified'],plan['media']['nvme_backups']):
        raise ValueError('Active baseline validation differs')
    rows=plan['historical_catalog'];new=[dict(path=publication['run']+'/'+r['saved_as'],
        bytes=r['bytes'],sha256=r['sha256']) for r in publication['backups']]
    new.extend(dict(path=publication['run']+'/'+core.NAMES[plan['media']['profile']][r['target']][2],
        bytes=r['old_bytes'],sha256=r['old_sha256']) for r in plan['media']['files'])
    combined=rows+new;catalog(combined)
    result=dict(format=RESULT,status='complete',plan_sha256=expected_plan_sha,
        checkpoint_sha256=plan['checkpoint_sha256'],publication=publication,
        historical_catalog=rows,historical_catalog_sha256=plan['historical_catalog_sha256'],
        historical_archives_reverified=False,active_baseline_archives_verified=plan['media']['nvme_backups'],
        newly_created_rollback_archives_verified=new,next_catalog=combined,next_catalog_sha256=seals.digest(combined),
        preserved_archive_count=len(rows),created_archive_count=len(new),deleted_archives=[],
        no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
    validate_result(result,plan,expected_plan_sha)
    path=Path(plan['media']['run'])/'result.json'
    with path.open('x') as out:json.dump(result,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return result


def same(left,right):
    """Strict JSON types: a numeric one cannot satisfy a true guard receipt."""
    if type(left) is not type(right):return False
    if isinstance(left,dict):return left.keys()==right.keys() and all(same(left[k],right[k]) for k in left)
    if isinstance(left,list):return len(left)==len(right) and all(same(a,b) for a,b in zip(left,right))
    return left==right


def validate_result(result,plan,expected_plan_sha):
    """Typed receipt replay only; never restarts audits or rehashes old archives.

    The controller must separately revalidate its checkpoint bytes. A matching
    receipt records completed checks at publication time, not proof that an old
    historical archive still has those contents now.
    """
    validate_plan(plan)
    if seals.digest(plan)!=expected_plan_sha:raise ValueError('Publication plan digest differs')
    p=plan['media'];core=bound_core(plan['tag']);names=core.NAMES[p['profile']]
    rows=plan['historical_catalog'];expected=dict(p['protected_files']);preserved={}
    for row in p['files']:
        n=row['target'];backup,_,nvme=names[n]
        expected[n]=row['new_sha256']
        if backup is not None:expected[backup]=row['old_sha256']
        preserved[n]=dict(sha256=row['old_sha256'],bytes=row['old_bytes'],sd_backup=backup,nvme_backup=nvme)
    extents=(('mbr','/dev/mmcblk0',512,'mbr.before-write.bin'),
        ('boot','/dev/mmcblk0p1',536870912,'boot-partition.before-write.img'),
        ('hfs','/dev/mmcblk0p2',134217728,'hfs-partition.before.img'))
    backups=[dict(device=node,bytes=size,sha256=p['protected_sha256'][kind],saved_as=name) for kind,node,size,name in extents]
    publication=result.get('publication',{});post=publication.get('protected_after',{})
    if set(post)!={'mbr','boot','hfs'}:raise ValueError('Three complete post-publication extents required')
    for kind,node,size,_ in extents:
        r=post[kind]
        if (set(r)!={'device','bytes','sha256','saved_as'} or r['device']!=node or
            type(r['bytes']) is not int or r['bytes']!=size or r['saved_as'] is not None or
            not isinstance(r['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',r['sha256']) or
            (kind!='boot' and r['sha256']!=p['protected_sha256'][kind])):
            raise ValueError('Post-publication extent or protected MBR/HFS differs')
    exact=dict(pair_publication_order=list(core.TARGETS),temporary_pair_published=True,
        reused_existing_sd_backups={original.REUSED_ZSH_BACKUP:original.GOOD_ZSH_SHA} if p['profile']==TRIAL else {},
        power_loss_atomicity_claimed=False,no_implicit_rollback=True,preserved_pair=preserved,
        pair_sha256={r['target']:r['new_sha256'] for r in p['files']},status='installed',run=p['run'],
        identity=dict(identity=p['identity_binding']['expected'],boot_id=p['linux_boot_id'],hostname='kamidana'),
        backups=backups,protected_after=post,protected_files_sha256=expected,
        active_baseline_archives_verified=p['nvme_backups'],boot_unmounted=True,
        no_hfs_mount=True,config_changed=True,no_reboot=True,firmware_changed=False,
        nvme_previous_pair_sha256={r['target']:r['old_sha256'] for r in p['files']})
    if not same(publication,exact):raise ValueError('Typed active-window publication receipt differs')
    new=[dict(path=p['run']+'/'+r['saved_as'],bytes=r['bytes'],sha256=r['sha256']) for r in backups]
    new.extend(dict(path=p['run']+'/'+names[r['target']][2],bytes=r['old_bytes'],sha256=r['old_sha256']) for r in p['files'])
    combined=rows+new;catalog(combined)
    exact=dict(format=RESULT,status='complete',plan_sha256=expected_plan_sha,
        checkpoint_sha256=plan['checkpoint_sha256'],publication=publication,
        historical_catalog=rows,historical_catalog_sha256=plan['historical_catalog_sha256'],
        historical_archives_reverified=False,active_baseline_archives_verified=p['nvme_backups'],
        newly_created_rollback_archives_verified=new,next_catalog=combined,next_catalog_sha256=seals.digest(combined),
        preserved_archive_count=len(rows),created_archive_count=5,deleted_archives=[],
        no_implicit_retry_or_rollback=True,power_loss_atomicity_claimed=False)
    if not same(result,exact):raise ValueError('Typed active-window archive receipt differs')
    return dict(typed_receipt_matches=True,historical_archives_reverified=False,
        new_hardware_read_performed=False,old_archive_payloads_read=0)


def legacy_read_budget(rows):
    catalog(rows);size=sum(r['bytes'] for r in rows)
    active=GOOD_FW_BYTES+original.GOOD_ZSH_BYTES
    return dict(historical_archives=len(rows),legacy_historical_hash_bytes_per_operation=2*size,
        v2_selected_baseline_hash_bytes_per_operation=2*active,
        avoided_historical_hash_bytes_per_operation=2*(size-active),
        current_raw_snapshots_and_rollback_checks_unchanged=True,measured_speedup=False)



