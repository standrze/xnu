#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Capture exact disposable HFS data after an admitted write and new SSD boot.

Default validates a local plan only. --execute reads SD through fixed read-only
descriptors and creates a fresh NVMe/local capture. No mount, repair, serial
input, staging, retry or reboot. The separate Mac image audit is still required.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import hfs_persistence_capture_core as core
import hfs_write_acceptance as acceptance
import serial_hfs_write_trial as recorder
import wait_nvme_linux as linux

installer = recorder.installer
ROOT = installer.ROOT
RUN_PATTERN = r'/home/sandrzej/xnu-gate4-hfs-persistence-[a-z0-9_]{8}'


def timestamp(value):
    date = datetime.fromisoformat(value)
    if date.tzinfo is None: raise ValueError('Timezone-qualified trial time required')
    return date


def local_image(name, expected):
    path = installer.evidence_path(str(ROOT / 'build/rpi5' / name / 'probe.bin'))
    if recorder.sha256(path) != expected: raise ValueError('Preserved local image differs: ' + name)
    return path.stat().st_size


def backup_rows(plan, installed):
    rows = []
    def add(directory, name, sha, size):
        if directory != '/home/sandrzej' and not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-(?:stage|boot|stats|write)-[a-z0-9_]{8}', directory):
            raise ValueError('Unexpected exact NVMe backup directory')
        if '/' in name or not re.fullmatch(r'[0-9a-f]{64}', sha) or type(size) is not int or not 0 < size <= 536870912:
            raise ValueError('Invalid fixed backup record')
        rows.append(dict(path=directory + '/' + name, bytes=size, sha256=sha))
    for row in installed['write_trial_backups']['before']:
        add(plan['run'], row['saved_as'], row['sha256'], row['bytes'])
    add(plan['backup_run'], 'mbr.before.bin', plan['original_mbr_sha256'], 512)
    add(plan['backup_run'], 'boot-partition.before.img', plan['boot_backup_sha256'], 536870912)
    add(plan['prior_boot_run'], 'sd-read-passed.bin', plan['passed_sd_image_sha256'],
        local_image('bl33-probe-unsh3788', plan['passed_sd_image_sha256']))
    add(plan['prior_correction_run'], 'hfs-statfs-failed.bin', plan['failed_hfs_image_sha256'],
        local_image('bl33-probe-qxmk1ban', plan['failed_hfs_image_sha256']))
    shell_sha = installer.checker.SHELL_BASELINE_SHA256
    shell = installer.evidence_path(str(ROOT / 'build/rpi5/shell-userland-20261011/probe.bin'))
    if recorder.sha256(shell) != shell_sha: raise ValueError('Preserved shell image differs')
    add('/home/sandrzej', 'xnu-shell-passed-backup-20261011.bin', shell_sha, shell.stat().st_size)
    ro_sha = installer.checker.HFS_READ_BASELINE_SHA256
    ro_size = local_image('bl33-probe-a5wng87t', ro_sha)
    if plan['profile'] in ('write-diagnostic','write-cache-diagnostic'):
        import stage_hfs_write_diagnostic as diagnostic
        w1_size = local_image('bl33-probe-ybis0sa6', diagnostic.PREVIOUS_IMAGE)
        if plan['profile']=='write-cache-diagnostic':
            import stage_hfs_cache_diagnostic as cache_diagnostic
            w2_size=local_image('bl33-probe-p8k9tahf',cache_diagnostic.PREVIOUS_IMAGE)
            add(plan['run'],'hfs-write-cache-probe-failed.bin',plan['old_image_sha256'],w2_size)
            add(plan['prior_cache_run'],'candidate.bin',cache_diagnostic.PREVIOUS_IMAGE,w2_size)
            add(plan['prior_cache_run'],'hfs-write-no-admission.bin',plan['no_admission_image_sha256'],w1_size)
        else:
            add(plan['run'], 'hfs-write-no-admission.bin', plan['old_image_sha256'], w1_size)
        add(plan['prior_write_run'], 'candidate.bin', diagnostic.PREVIOUS_IMAGE, w1_size)
        add(plan['prior_write_run'], 'hfs-read-passed.bin', ro_sha, ro_size)
        sizes = {'mbr.before-write.bin': 512, 'boot-partition.before-write.img': 536870912,
                 'hfs-partition.before.img': core.IMAGE_BYTES}
        for name, sha in plan['prior_write_backup_sha256'].items(): add(plan['prior_write_run'], name, sha, sizes[name])
        if plan['profile']=='write-cache-diagnostic':
            for name,sha in plan['prior_cache_backup_sha256'].items(): add(plan['prior_cache_run'],name,sha,sizes[name])
    else:
        add(plan['run'], 'hfs-read-passed.bin', plan['old_image_sha256'], ro_size)
    candidate = installer.evidence_path(plan['candidate'])
    if recorder.sha256(candidate) != plan['new_image_sha256']: raise ValueError('Installed candidate bytes differ')
    add(plan['run'], 'candidate.bin', plan['new_image_sha256'], candidate.stat().st_size)
    if len({row['path'] for row in rows}) != len(rows): raise ValueError('Repeated backup record')
    return rows


def load_plan(inputs, installed_dir, trial_path, now=None):
    path = installer.evidence_path(str(trial_path)); state_bytes = path.read_bytes(); state = json.loads(state_bytes)
    state_sha256 = hashlib.sha256(state_bytes).hexdigest()
    if state.get('status') != 'batch_passed_not_durability':
        raise ValueError('Actual admitted write/unmount trial must pass before post-reboot capture')
    started, ended = timestamp(state['started_utc']), timestamp(state['ended_utc'])
    now = now or datetime.now(timezone.utc)
    if not 0 < (ended - started).total_seconds() <= 7200 or ended > now:
        raise ValueError('Write trial chronology is incomplete or in the future')
    # Historical audit at ACTUAL launch time, not permission to install/write
    # using an old reference today. Remote current-root/new-boot checks remain.
    plan, installed, bound = recorder.load_inputs(inputs, installed_dir, now=started)
    raw_path = installer.evidence_path(str(path.with_name('serial.bin')))
    if raw_path.stat().st_size > 64 * 1024 * 1024: raise ValueError('Oversized physical write transcript')
    raw = raw_path.read_bytes()
    if state.get('recorder_source_sha256') != recorder.sha256(Path(recorder.__file__)):
        raise ValueError('Write recorder source differs from the actual launch')
    proof = acceptance.validate(state, raw, plan, installed, bound)
    backups = backup_rows(plan, installed)
    if recorder.sha256(path) != state_sha256 or recorder.sha256(raw_path) != proof['serial_sha256']:
        raise ValueError('Physical write state/raw changed during evidence validation')
    return dict(host=linux.HOST, expected=plan['expected'], linux_boot_id_before_write=plan['linux_boot_id'],
                mbr_sha256=installed['write_trial_backups']['after']['mbr']['sha256'],
                boot_sha256=installed['write_trial_backups']['after']['boot']['sha256'],
                fixture_sha256=plan['fixture_sha256'], nvme_backups=backups,
                image_sha256_at_boot=plan['new_image_sha256'], physical_write_acceptance=proof,
                write_trial_ended_utc=state['ended_utc'], trial_state_sha256=state_sha256,
                write_installation_sha256=bound, no_sd_mount=True, no_sd_write=True, no_reboot=True,
                durability_verified=False)


def remote_source(plan):
    if (not re.fullmatch(RUN_PATTERN, plan['run']) or
            plan['linux_boot_id_after_write'] == plan['linux_boot_id_before_write']):
        raise ValueError('Exact fresh NVMe directory and distinct actual Linux boot required')
    return (Path(core.__file__).read_text() + '\nPLAN=json.loads(' + repr(json.dumps(plan)) + ')\n' +
            'print(json.dumps(run_capture(PLAN)))\n')


def validate_report(report, plan):
    expected = dict(status='captured_not_durability', run=plan['run'],
                    identity=dict(identity=plan['expected'], boot_id=plan['linux_boot_id_after_write'], hostname='kamidana'),
                    nvme_backups_verified=plan['nvme_backups'], sd_write_operations=0, sd_mount_operations=0,
                    image=plan['run'] + '/' + core.IMAGE_NAME, durability_verified=False)
    if any(type(report.get(key)) is not type(value) or report[key] != value for key, value in expected.items()):
        raise ValueError('Incomplete independent post-write capture result')
    for key, node, size, sha in (('mbr', '/dev/mmcblk0', 512, plan['mbr_sha256']),
                                 ('boot', '/dev/mmcblk0p1', 536870912, plan['boot_sha256'])):
        if report.get('protected', {}).get(key) != dict(device=node, bytes=size, sha256=sha):
            raise ValueError('Full protected raw SD MBR/FAT differs')
    sha = report.get('image_sha256', '')
    first = dict(device='/dev/mmcblk0p2', bytes=core.IMAGE_BYTES, sha256=sha)
    if (not re.fullmatch(r'[0-9a-f]{64}', sha) or sha == plan['fixture_sha256'] or
            report.get('hfs_reads') != [first, dict(first, saved_as=core.IMAGE_NAME), first] or
            any(type(row.get('bytes')) is not int for row in report['hfs_reads'])):
        raise ValueError('Require three complete stable changed-HFS partition reads')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--installed', required=True, type=Path)
    parser.add_argument('--trial', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    output = args.output.absolute()
    if output.is_symlink() or not output.resolve().is_relative_to(ROOT / 'build/rpi5') or output.exists():
        raise ValueError('Use a fresh local build/rpi5 capture directory')
    plan = load_plan(args.inputs, args.installed, args.trial)
    output.mkdir()
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(output)); return 0
    if load_plan(args.inputs, args.installed, args.trial) != plan:
        raise ValueError('Physical write/installation evidence changed before capture')
    ssh = installer.boot.SSH
    response = subprocess.run(ssh + [linux.COMMAND], text=True, capture_output=True, timeout=15, check=True)
    ready = linux.identity(response.stdout)
    if ready['boot_id'] == plan['linux_boot_id_before_write']:
        raise ValueError('No intervening actual new SSD Linux boot')
    plan['linux_boot_id_after_write'] = ready['boot_id']
    plan['linux_verified_utc'] = datetime.now(timezone.utc).isoformat()
    prepare = installer.boot.fixture_stage.PREPARE.replace("prefix='xnu-gate4-hfs-stage-'", "prefix='xnu-gate4-hfs-persistence-'")
    response = subprocess.run(ssh + ['python3 -'], input=prepare, text=True, capture_output=True, timeout=30, check=True)
    plan['run'] = json.loads(response.stdout)['run']
    source = remote_source(plan)
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    (output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        response = subprocess.run(ssh + ['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, value in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (output / name).write_bytes(value.encode() if isinstance(value, str) else value or b'')
        (output / 'outcome-unknown.txt').write_text('Inspect the existing NVMe run; never automatically retry.\n')
        raise
    (output / 'remote.stdout').write_text(response.stdout); (output / 'remote.stderr').write_text(response.stderr)
    response.check_returncode()
    report = json.loads(response.stdout); validate_report(report, plan)
    (output / 'remote-result.json').write_text(json.dumps(report, indent=2) + '\n')
    image = output / core.IMAGE_NAME
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    linux.HOST + ':' + report['image'], str(image)], check=True, timeout=180)
    from prepare_hfs_fixture import inspect_image
    header = inspect_image(image)
    if recorder.sha256(image) != report['image_sha256']:
        raise ValueError('Complete local partition capture differs from remote readback')
    response = subprocess.run(ssh + [linux.COMMAND], text=True, capture_output=True, timeout=15, check=True)
    if linux.identity(response.stdout) != ready:
        raise ValueError('Linux boot/root changed during partition transfer')
    if load_plan(args.inputs, args.installed, args.trial) != {key: value for key, value in plan.items()
            if key not in ('run', 'linux_boot_id_after_write', 'linux_verified_utc')}:
        raise ValueError('Physical write evidence changed during capture')
    report.update(local_image=str(image), volume_header=header, plan_sha256=recorder.sha256(output / 'plan.json'),
                  captured_utc=datetime.now(timezone.utc).isoformat(), capture_source_sha256=recorder.sha256(Path(__file__)),
                  remote_source_sha256=hashlib.sha256(source.encode()).hexdigest())
    (output / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
