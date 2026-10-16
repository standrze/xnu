#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guarded fixed-card watchdog staging or explicit zsh restoration, plan by default."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_recovery_package as package
import check_socket_identity_package as socket_package
import stage_socket_identity_trial as prior
import capture_pcie_recovery_reference as history
import recovery_trial_install_core as core
import pcie_recovery_reference_core as reference

ROOT, HOST, SSH = prior.ROOT, prior.HOST, prior.SSH
PACKAGE = ROOT/'build/rpi5/pm-recovery-bro7oklj'
IMAGE_SHA = 'a616420b2c243182aeed6d04b49f0ebab416f88a54303b9805aaa82ab90d8ba2'
MANIFEST_SHA = '9561227bec1811f23ef2c9a1bc245ea0159df085c38a82db17f7f1a2a9d6e30d'
SOCKET = ROOT/'build/rpi5/bl33-probe-vszhh6o4'
MODULES = (prior.base.capture, prior.base.install_core, prior.base.snapshots, reference, core)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def source_pins():
    modules = (Path(__file__), *(Path(m.__file__) for m in MODULES), Path(prior.__file__),
        Path(history.__file__), Path(package.__file__), Path(socket_package.__file__),
        ROOT/'tools/rpi5/tests/test_watchdog_recovery_install.py')
    return {str(p):sha(p) for p in modules}


def inherited(plan, result, old_bytes, previous_name, expected_count):
    rows = copy.deepcopy(plan['nvme_backups'])
    rows.extend(dict(path=result['run']+'/'+r['saved_as'], bytes=r['bytes'], sha256=r['sha256']) for r in result['backups'])
    rows.append(dict(path=result['run']+'/'+previous_name, bytes=old_bytes, sha256=result['preserved_sd_image_sha256']))
    if len(rows) != expected_count or len({r['path'] for r in rows}) != expected_count:
        raise ValueError('Incomplete/duplicate backup chain')
    return rows


def load_plan(boot_id, restore_from=None):
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id): raise ValueError('SSD boot UUID required')
    report = package.inspect(PACKAGE)
    if report['image_sha256'] != IMAGE_SHA or report['manifest_sha256'] != MANIFEST_SHA:
        raise ValueError('Exact accepted watchdog-only package required')
    if restore_from is None:
        history.load_plan(boot_id) # Pinned installed history and validator, no network.
        plan = json.loads((history.HISTORY/'plan.json').read_text())
        result = json.loads((history.HISTORY/'result.json').read_text())
        old = ROOT/'build/rpi5/bl33-probe-i3d1ah4e/probe.bin'
        if sha(old) != prior.OLD_SHA: raise ValueError('Inherited Apple-network image changed')
        rows = inherited(plan, result, old.stat().st_size, prior.PREVIOUS_NAME, 44)
        old_hash, new_hash, candidate = prior.NEW_SHA, IMAGE_SHA, report['image']
        profile, preflight = 'watchdog-only-trial', report
        ancestry = dict(directory=str(history.HISTORY), hashes=history.HISTORY_SHA)
    else:
        directory = restore_from.resolve()
        if directory.parent != ROOT/'build/rpi5': raise ValueError('Local installation receipt required')
        plan = json.loads((directory/'plan.json').read_text()); result = json.loads((directory/'result.json').read_text())
        validate_result(result, plan)
        if plan['profile'] != 'watchdog-only-trial' or plan['new_image_sha256'] != IMAGE_SHA:
            raise ValueError('Exact prior watchdog-only staging required')
        if boot_id == plan['linux_boot_id']: raise ValueError('Distinct Linux return required before restoration')
        rows = inherited(plan, result, 19384000, core.NAMES['watchdog-only-trial'][2], 48)
        preflight = socket_package.inspect(SOCKET)
        if preflight['image_sha256'] != prior.NEW_SHA: raise ValueError('Exact working zsh package required')
        old_hash, new_hash, candidate = IMAGE_SHA, prior.NEW_SHA, preflight['image']
        profile = 'watchdog-only-restore'
        ancestry = dict(directory=str(directory), hashes={n:sha(directory/n) for n in ('plan.json', 'result.json')})
    binding = copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write'] = result['identity']['boot_id']
    binding['linux_boot_id_after_write'] = boot_id
    if binding['linux_boot_id_before_write'] == boot_id: raise ValueError('Intervening SSD boot required')
    protected = dict(result['protected_files_sha256']); del protected['probe.bin']
    return dict(host=HOST, profile=profile, candidate=candidate, old_image_sha256=old_hash,
        new_image_sha256=new_hash, linux_boot_id=boot_id, identity_binding=binding,
        nvme_backups=rows, protected_sha256={k:r['sha256'] for k,r in result['protected_after'].items()},
        protected_files=protected, preflight=preflight, ancestry=ancestry, source_sha256=source_pins(),
        no_hfs_mount=True, no_config_change=True, no_pcie_access=True, no_reboot=True)


def remote_source(plan):
    if source_pins() != plan['source_sha256']: raise ValueError('Source changed')
    source = 'import types,json\n'
    for name, module in zip(('capture', 'helper', 'snapshots', 'reference', 'trial'), MODULES):
        source += f'{name}=types.ModuleType({name!r})\nexec('+repr(Path(module.__file__).read_text())+f',{name}.__dict__)\n'
    return source+'PLAN=json.loads('+repr(json.dumps(plan))+')\nprint(json.dumps(trial.execute(PLAN,capture,helper,snapshots,reference)))\n'


def validate_result(result, plan):
    profile = plan['profile']
    if profile not in core.NAMES: raise ValueError('Wrong profile')
    backup = core.NAMES[profile][0]
    required = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
        preserved_sd_image_sha256=plan['old_image_sha256'], nvme_previous_image_sha256=plan['old_image_sha256'],
        boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
        power_loss_atomicity_claimed=False, temporary_published=True, sd_backup=backup,
        nvme_backups_verified=plan['nvme_backups'])
    if any(not reference.same(result.get(k), v) for k,v in required.items()): raise ValueError('Incomplete installation receipt')
    expected = dict(plan['protected_files'], **{'probe.bin':plan['new_image_sha256'], backup:plan['old_image_sha256']})
    identity = dict(identity=plan['identity_binding']['expected'], boot_id=plan['linux_boot_id'], hostname='kamidana')
    if not reference.same(result.get('identity'), identity) or result.get('protected_files_sha256') != expected:
        raise ValueError('Post-install identity/files differ')
    records = [dict(device=node, bytes=length, sha256=plan['protected_sha256'][key], saved_as=name)
               for key,node,_,length,name in core.EXTENTS]
    if result.get('backups') != records: raise ValueError('Fresh full snapshots incomplete')
    for key,node,_,length,_ in core.EXTENTS:
        row = result.get('protected_after', {}).get(key, {})
        if row.get('device') != node or type(row.get('bytes')) is not int or row['bytes'] != length or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')):
            raise ValueError('Post-install raw coverage incomplete')
        if key != 'boot' and row['sha256'] != plan['protected_sha256'][key]: raise ValueError('Protected MBR/HFS changed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linux-boot-id', required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--restore-from', type=Path); parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    out = args.output.resolve()
    if out.parent != ROOT/'build/rpi5': raise ValueError('Fresh local build/rpi5 child required')
    plan = load_plan(args.linux_boot_id, args.restore_from)
    out.mkdir(exist_ok=False)
    archived = out/'source-snapshots'; archived.mkdir()
    for name,pin in plan['source_sha256'].items():
        target = archived/Path(name).name; shutil.copyfile(name, target)
        if sha(target) != pin: raise ValueError('Snapshot source drift')
    def save(): (out/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    save()
    if not args.execute: print('LOCAL_PLAN_ONLY '+str(out)); return 0
    if load_plan(args.linux_boot_id, args.restore_from) != plan: raise ValueError('Inputs changed before SSH')
    prepare = prior.PREPARE.replace("prefix='xnu-gate6-socket-id-'", "prefix='xnu-gate5-watchdog-'")
    response = subprocess.run(SSH+['python3 -'], input=prepare, text=True, capture_output=True, check=True, timeout=30)
    work = json.loads(response.stdout)['run']
    if not re.fullmatch('/home/sandrzej/xnu-gate5-watchdog-[a-z0-9_]{8}', work): raise ValueError('Unexpected SSD directory')
    plan['run'] = work; save()
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
        plan['candidate'], HOST+':'+work+'/candidate.bin'], check=True, timeout=60)
    source = remote_source(plan)
    (out/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response = subprocess.run(SSH+['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (out/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (out/'outcome-unknown.txt').write_text('Inspect existing run and mount state. Do not retry, reboot or restore blindly.\n')
        raise
    (out/'remote.stdout').write_text(response.stdout); (out/'remote.stderr').write_text(response.stderr)
    response.check_returncode(); result = json.loads(response.stdout); validate_result(result, plan)
    if source_pins() != plan['source_sha256']: raise ValueError('Source changed during installation')
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n'); print(out)
    return 0


if __name__ == '__main__': raise SystemExit(main())
