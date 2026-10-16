#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve accepted zsh and stage the distinct Apple-tool root; plan by default.

Reuse exact-card/full-snapshot installation. No reboot, repair or rollback.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

try:
    from . import stage_zsh_metadata_trial as previous
    from . import check_apple_network_package as package_check
except ImportError:
    import stage_zsh_metadata_trial as previous
    import check_apple_network_package as package_check

base = previous.base
ROOT, HOST, SSH = base.ROOT, base.HOST, base.SSH
HISTORY = ROOT/'build/rpi5/zsh-metadata-installed-20261012'
HISTORY_SHA = {'plan.json':'a3351305fb88c445b0979098b4ce25c043c1f6af3ad766d99376a5129997e433',
               'result.json':'c93c515375365984715585a849c383ffee1894588d4735202d1d93f56f32a7dc'}
OLD_SHA = '352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa'
NEW_SHA = 'b67b8013361b94b1874d7f0bbe6013d1c8efc99ca37b0debf7bc0012915f9ce8'
FAT_SHA = '18b6fdf87a5438df040c1266189ea6cb1f4420a44448b5c8d4d7c8eaf6f89e09'
PREVIOUS_NAME = 'zsh-metadata-passed.bin'
PROFILE = 'apple-network-trial'


def remote_template():
    source = previous.remote_template()
    if source.count(repr(previous.PREVIOUS_NAME)) != 3 or source.count(",'zsh-metadata-trial')") != 1:
        raise ValueError('Reviewed metadata installation template changed')
    return source.replace(repr(previous.PREVIOUS_NAME),repr(PREVIOUS_NAME)).replace(
        ",'zsh-metadata-trial')", ",'apple-network-trial')")


if previous.PREPARE.count("prefix='xnu-gate6-metadata-'") != 1:
    raise ValueError('Reviewed SSD preparation template changed')
PREPARE = previous.PREPARE.replace("prefix='xnu-gate6-metadata-'","prefix='xnu-gate6-apple-net-'")


def load_plan(package, boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot_id):
        raise ValueError('Fresh verified SSD Linux boot UUID required')
    for name,pin in HISTORY_SHA.items():
        if base.terminal.sha256(HISTORY/name) != pin:
            raise ValueError('Accepted metadata installation history changed')
    plan = json.loads((HISTORY/'plan.json').read_text())
    result = json.loads((HISTORY/'result.json').read_text())
    previous.validate_result(result,plan)
    if result['image_sha256'] != OLD_SHA or result['protected_after']['boot']['sha256'] != FAT_SHA:
        raise ValueError('Not the accepted zsh metadata baseline')
    if boot_id == result['identity']['boot_id']:
        raise ValueError('Distinct SSD Linux return required')
    report = package_check.inspect(package)
    if report['image_sha256'] != NEW_SHA or report['image_bytes'] != 19334848:
        raise ValueError('Exact prepared Apple network image required')
    binding = copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write'] = result['identity']['boot_id']
    binding['linux_boot_id_after_write'] = boot_id
    backups = copy.deepcopy(plan['nvme_backups'])
    backups.extend(dict(path=result['run']+'/'+row['saved_as'],bytes=row['bytes'],sha256=row['sha256'])
                   for row in result['backups'])
    prior = ROOT/'build/rpi5/bl33-probe-cijenc9s/probe.bin'
    if base.terminal.sha256(prior) != previous.OLD_SHA:
        raise ValueError('Preserved metadata diagnostic image changed')
    backups.append(dict(path=result['run']+'/'+previous.PREVIOUS_NAME,
                        bytes=prior.stat().st_size,sha256=previous.OLD_SHA))
    if len(backups) != 36 or len({row['path'] for row in backups}) != 36:
        raise ValueError('Incomplete/duplicate preservation chain')
    protected = dict(result['protected_files_sha256']); del protected['probe.bin']
    sources = [Path(__file__),Path(previous.__file__),Path(base.capture.__file__),
               Path(base.install_core.__file__),Path(base.snapshots.__file__),Path(package_check.__file__)]
    return dict(host=HOST,profile=PROFILE,candidate=report['image'],
                old_image_sha256=OLD_SHA,new_image_sha256=NEW_SHA,linux_boot_id=boot_id,
                identity_binding=binding,nvme_backups=backups,
                protected_sha256={key:row['sha256'] for key,row in result['protected_after'].items()},
                protected_files=protected,preflight=report,history_sha256=HISTORY_SHA,
                source_sha256={str(path):base.terminal.sha256(path) for path in sources},
                no_hfs_mount=True,no_pcie_access=True,no_config_change=True,no_reboot=True)


def remote_source(plan):
    for name,pin in plan['source_sha256'].items():
        if base.terminal.sha256(Path(name)) != pin:
            raise ValueError('Staging source changed before execution')
    sources = [Path(base.capture.__file__),Path(base.install_core.__file__),Path(base.snapshots.__file__)]
    return '\n'.join(path.read_text() for path in sources)+'\nPLAN=json.loads('+repr(json.dumps(plan))+')\n'+remote_template()


def validate_result(result,plan):
    return previous.previous.validate_profile_result(result,plan,PROFILE,OLD_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('--linux-boot-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'build/rpi5'):
        parser.error('New local build/rpi5 output directory required')
    plan = load_plan(args.package,args.linux_boot_id)
    args.output.mkdir(parents=True,exist_ok=False)
    def save(): (args.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    save()
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS '+str(args.output)); return 0
    if load_plan(args.package,args.linux_boot_id) != plan:
        raise ValueError('Inputs changed before SSH')
    prepared = subprocess.run(SSH+['python3 -'],input=PREPARE,text=True,capture_output=True,check=True,timeout=30)
    run = json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate6-apple-net-[a-z0-9_]{8}',run):
        raise ValueError('Unexpected SSD installation directory')
    plan['run'] = run; save()
    subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                    plan['candidate'],HOST+':'+run+'/candidate.bin'],check=True,timeout=120)
    source = remote_source(plan)
    (args.output/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response = subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (args.output/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (args.output/'outcome-unknown.txt').write_text('Inspect existing remote run; do not repeat or roll back.\n')
        raise
    for name,value in (('remote.stdout',response.stdout),('remote.stderr',response.stderr)):
        (args.output/name).write_text(value)
    response.check_returncode()
    result = json.loads(response.stdout); validate_result(result,plan)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(args.output)
    return 0


if __name__ == '__main__': raise SystemExit(main())
