#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed-card zsh trial staging. Plan-only unless --execute; no reboot/retry."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_zsh_trial_package as package_check
import stage_pcie_topology as previous

ROOT, HOST, SSH = previous.ROOT, previous.HOST, previous.SSH
HISTORY = ROOT / 'build/rpi5/pcie-topology-installed-20261012'
HISTORY_SHA = {'plan.json': '2f95ac4ebc101db24353c791d8a9a31aa4d29b3d0c2942c6bdb04a7ad018a913',
               'result.json': '329c4c4bf151700824d71429d920a8d81f0e3c4341c0ca728f7d3100e1645c78'}
OLD_SHA = '038c2b9bd0b55fa35496632fad7a96e8ffff1f2a7b64006e5709757bd895b895'
FAT_SHA = 'b200d1fcc91a2e36ba700b9967a8c5efc79c43a616575e7ce6286f98b98ade60'
PREVIOUS_NAME = 'pcie-topology-passed.bin'


def remote_template():
    # Reuse the audited fixed-device mount/snapshot/preservation algorithm,
    # substituting ONLY the distinct regular-file profile and prior-image name.
    # Refuse template drift instead of silently rendering a partial substitution.
    source = previous.REMOTE
    if source.count("'hfs-cache-buffer-failed.bin'") != 3 or source.count(",'pcie-topology')") != 1:
        raise ValueError('Previous remote template changed; review rather than guess')
    return source.replace("'hfs-cache-buffer-failed.bin'", repr(PREVIOUS_NAME)).replace(
        ",'pcie-topology')", ",'zsh-trial')")


PREPARE = previous.PREPARE.replace("prefix='xnu-gate5-topology-'", "prefix='xnu-gate6-zsh-'")


def load_plan(package, boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id):
        raise ValueError('Fresh verified SSD Linux boot UUID required')
    for name, expected in HISTORY_SHA.items():
        if previous.terminal.sha256(HISTORY / name) != expected:
            raise ValueError('Pinned topology installation history changed')
    plan = json.loads((HISTORY / 'plan.json').read_text())
    result = json.loads((HISTORY / 'result.json').read_text())
    previous.validate_result(result, plan)
    if result['image_sha256'] != OLD_SHA or result['protected_after']['boot']['sha256'] != FAT_SHA:
        raise ValueError('Not the accepted topology baseline')
    if boot_id == result['identity']['boot_id']:
        raise ValueError('Topology boot must have returned to a distinct SSD Linux boot')
    report = package_check.inspect(package)
    binding = copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write'] = result['identity']['boot_id']
    binding['linux_boot_id_after_write'] = boot_id
    backups = copy.deepcopy(plan['nvme_backups'])
    for row in result['backups']:
        backups.append(dict(path=result['run'] + '/' + row['saved_as'], bytes=row['bytes'], sha256=row['sha256']))
    w3_records = [row for row in plan['nvme_backups'] if row['sha256'] == previous.W3]
    if len(w3_records) != 1:
        raise ValueError('Preserved W3 size must come from the pinned history')
    backups.append(dict(path=result['run'] + '/hfs-cache-buffer-failed.bin',
                        bytes=w3_records[0]['bytes'], sha256=previous.W3))
    if len(backups) != 24 or len({row['path'] for row in backups}) != 24:
        raise ValueError('Incomplete or duplicate preservation chain')
    protected = dict(result['protected_files_sha256'])
    del protected['probe.bin']
    sources = [Path(__file__), Path(previous.__file__), Path(previous.capture.__file__),
               Path(previous.install_core.__file__), Path(previous.snapshots.__file__),
               Path(package_check.__file__)]
    return dict(host=HOST, profile='zsh-trial', candidate=report['image'],
                old_image_sha256=OLD_SHA, new_image_sha256=report['image_sha256'],
                linux_boot_id=boot_id, identity_binding=binding, nvme_backups=backups,
                protected_sha256={key: row['sha256'] for key, row in result['protected_after'].items()},
                protected_files=protected, preflight=report, history_sha256=HISTORY_SHA,
                source_sha256={str(p): previous.terminal.sha256(p) for p in sources},
                no_hfs_mount=True, no_pcie_access=True, no_config_change=True, no_reboot=True)


def remote_source(plan):
    for name, sha in plan['source_sha256'].items():
        if previous.terminal.sha256(Path(name)) != sha:
            raise ValueError('Staging source changed before execution')
    sources = [Path(previous.capture.__file__), Path(previous.install_core.__file__), Path(previous.snapshots.__file__)]
    return '\n'.join(path.read_text() for path in sources) + '\nPLAN=json.loads(' + repr(json.dumps(plan)) + ')\n' + remote_template()


def validate_result(result, plan):
    backup = previous.install_core.INSTALL_NAMES['zsh-trial'][0]
    required = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
                    preserved_sd_image_sha256=OLD_SHA, nvme_previous_image_sha256=OLD_SHA,
                    boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
                    power_loss_atomicity_claimed=False, temporary_published=True, sd_backup=backup,
                    nvme_backups_verified=plan['nvme_backups'])
    if any(type(result.get(k)) is not type(v) or result[k] != v for k, v in required.items()):
        raise ValueError('Incomplete staging outcome; inspect existing run, never retry')
    files = dict(plan['protected_files'], **{'probe.bin': plan['new_image_sha256'], backup: OLD_SHA})
    identity = dict(identity=plan['identity_binding']['expected'], boot_id=plan['linux_boot_id'], hostname='kamidana')
    if result.get('identity') != identity or result.get('protected_files_sha256') != files:
        raise ValueError('Post-install identity or protected files differ')
    rows = [('mbr','/dev/mmcblk0',512,'mbr.before-write.bin'),
            ('boot','/dev/mmcblk0p1',536870912,'boot-partition.before-write.img'),
            ('hfs','/dev/mmcblk0p2',134217728,'hfs-partition.before.img')]
    expected = [dict(device=node, bytes=size, sha256=plan['protected_sha256'][key], saved_as=name)
                for key, node, size, name in rows]
    if result.get('backups') != expected:
        raise ValueError('Fresh full NVMe snapshots are incomplete')
    for key, node, size, _ in rows:
        row = result.get('protected_after', {}).get(key, {})
        if row.get('device') != node or row.get('bytes') != size or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')):
            raise ValueError('Post-install raw protection coverage incomplete')
        if key != 'boot' and row['sha256'] != plan['protected_sha256'][key]:
            raise ValueError('Protected MBR/HFS bytes changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--linux-boot-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'build/rpi5'):
        parser.error('New local build/rpi5 output directory required')
    plan = load_plan(args.package, args.linux_boot_id)
    args.output.mkdir(parents=True, exist_ok=False)
    def save():
        (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    save()
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(args.output))
        return 0
    if load_plan(args.package, args.linux_boot_id) != plan:
        raise ValueError('Inputs changed before SSH')
    prepared = subprocess.run(SSH + ['python3 -'], input=PREPARE, text=True, capture_output=True, check=True, timeout=30)
    run = json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate6-zsh-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected remote installation directory')
    plan['run'] = run
    save()
    subprocess.run(['scp', '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                    plan['candidate'], HOST + ':' + run + '/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (args.output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        response = subprocess.run(SSH + ['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, value in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (args.output / name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (args.output / 'outcome-unknown.txt').write_text('Inspect existing remote run; do not repeat or roll back automatically.\n')
        raise
    for name, value in (('remote.stdout', response.stdout), ('remote.stderr', response.stderr)):
        (args.output / name).write_text(value)
    response.check_returncode()
    result = json.loads(response.stdout)
    validate_result(result, plan)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
