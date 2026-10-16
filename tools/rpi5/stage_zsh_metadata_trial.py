#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct storage-off metadata correction; plan-only unless --execute.

Fixed disposable card, current diagnostic baseline, full NVMe preservation.
No reboot, retry, repair, firmware edit, HFS mount or automatic rollback.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_zsh_metadata_package as package_check
import stage_statprobe_trial as previous

base = previous.base
ROOT, HOST, SSH = base.ROOT, base.HOST, base.SSH
HISTORY = ROOT / 'build/rpi5/statprobe-trial-installed-20261012'
HISTORY_SHA = {
    'plan.json': '28d0e861d7f7922ab0530973599c1adbdbb39e3c7a2119f8424be75f86e78414',
    'result.json': 'c6ed4a222de1232d55eb69462b4918c8a553a328094e54f8007dee80f50c4c3b',
}
OLD_SHA = '822e52de88303be9edfe20dec51d14fe1476a0604c77040b56d6254f1a953e99'
FAT_SHA = '60b6ed08168bce63d5420665f955d56e958754f54e0f30ec861c940933413b52'
PREVIOUS_NAME = 'statprobe-diagnosed.bin'
PROFILE = 'zsh-metadata-trial'


def remote_template():
    source = previous.remote_template()
    old = repr(previous.PREVIOUS_NAME)
    if source.count(old) != 3 or source.count(",'statprobe-trial')") != 1:
        raise ValueError('Reviewed diagnostic installer template changed')
    return source.replace(old, repr(PREVIOUS_NAME)).replace(",'statprobe-trial')", ",'zsh-metadata-trial')")


if previous.PREPARE.count("prefix='xnu-gate6-statprobe-'") != 1:
    raise ValueError('Reviewed SSD preparation template changed')
PREPARE = previous.PREPARE.replace("prefix='xnu-gate6-statprobe-'", "prefix='xnu-gate6-metadata-'")


def load_plan(package, boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id):
        raise ValueError('Fresh verified SSD Linux boot UUID required')
    for name, expected in HISTORY_SHA.items():
        if base.terminal.sha256(HISTORY/name) != expected:
            raise ValueError('Pinned diagnostic installation history changed')
    plan = json.loads((HISTORY/'plan.json').read_text())
    result = json.loads((HISTORY/'result.json').read_text())
    previous.validate_result(result, plan)
    if result['image_sha256'] != OLD_SHA or result['protected_after']['boot']['sha256'] != FAT_SHA:
        raise ValueError('Not the physically diagnosed baseline')
    if boot_id == result['identity']['boot_id']:
        raise ValueError('Requires a distinct return to SSD Linux')
    report = package_check.inspect(package)
    binding = copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write'] = result['identity']['boot_id']
    binding['linux_boot_id_after_write'] = boot_id
    backups = copy.deepcopy(plan['nvme_backups'])
    backups.extend(dict(path=result['run']+'/'+row['saved_as'], bytes=row['bytes'], sha256=row['sha256'])
                   for row in result['backups'])
    prior = ROOT/'build/rpi5/bl33-probe-_qoqmu9u/probe.bin'
    if base.terminal.sha256(prior) != previous.OLD_SHA:
        raise ValueError('Preserved physically interactive zsh image changed')
    backups.append(dict(path=result['run']+'/'+previous.PREVIOUS_NAME,
                        bytes=prior.stat().st_size, sha256=previous.OLD_SHA))
    if len(backups) != 32 or len({row['path'] for row in backups}) != 32:
        raise ValueError('Incomplete or duplicate preservation chain')
    protected = dict(result['protected_files_sha256'])
    del protected['probe.bin']
    sources = [Path(__file__), Path(previous.__file__), Path(previous.previous.__file__),
               Path(base.__file__), Path(base.capture.__file__), Path(base.install_core.__file__),
               Path(base.snapshots.__file__), Path(package_check.__file__),
               Path(package_check.previous.__file__), Path(package_check.guard.__file__)]
    sources.extend(ROOT/'tools/rpi5'/name for name in
                   ('check_hfs_stats_package.py','audit_macho.py','audit_statprobe_metadata.py'))
    return dict(host=HOST, profile=PROFILE, candidate=report['image'],
                old_image_sha256=OLD_SHA, new_image_sha256=report['image_sha256'],
                linux_boot_id=boot_id, identity_binding=binding, nvme_backups=backups,
                protected_sha256={key: row['sha256'] for key,row in result['protected_after'].items()},
                protected_files=protected, preflight=report, history_sha256=HISTORY_SHA,
                source_sha256={str(p): base.terminal.sha256(p) for p in sources},
                no_hfs_mount=True, no_pcie_access=True, no_config_change=True, no_reboot=True)


def remote_source(plan):
    for name, sha in plan['source_sha256'].items():
        if base.terminal.sha256(Path(name)) != sha:
            raise ValueError('Staging source changed before execution')
    sources = [Path(base.capture.__file__), Path(base.install_core.__file__), Path(base.snapshots.__file__)]
    return '\n'.join(path.read_text() for path in sources)+'\nPLAN=json.loads('+repr(json.dumps(plan))+')\n'+remote_template()


def validate_result(result, plan):
    return previous.validate_profile_result(result, plan, PROFILE, OLD_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--linux-boot-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'build/rpi5'):
        parser.error('New local build/rpi5 output directory required')
    plan = load_plan(args.package, args.linux_boot_id)
    args.output.mkdir(parents=True, exist_ok=False)
    def save():
        (args.output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    save()
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS '+str(args.output))
        return 0
    if load_plan(args.package, args.linux_boot_id) != plan:
        raise ValueError('Inputs changed before SSH')
    prepared = subprocess.run(SSH+['python3 -'], input=PREPARE, text=True,
                              capture_output=True, check=True, timeout=30)
    run = json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate6-metadata-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected remote installation directory')
    plan['run'] = run
    save()
    subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                    plan['candidate'],HOST+':'+run+'/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (args.output/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response = subprocess.run(SSH+['sudo -n python3 -'], input=source,
                                  text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (args.output/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (args.output/'outcome-unknown.txt').write_text('Inspect existing remote run; do not repeat or roll back automatically.\n')
        raise
    for name,value in (('remote.stdout',response.stdout),('remote.stderr',response.stderr)):
        (args.output/name).write_text(value)
    response.check_returncode()
    result = json.loads(response.stdout)
    validate_result(result, plan)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
