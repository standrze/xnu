#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guarded distinct write-image installation; local plan unless --execute.

Preserves the accepted RO image and full data/boot snapshots on exact SSD Linux.
Never mounts HFS, changes partitions/config, reboots, retries or rolls back.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import capture_hfs_reference as reference
import check_hfs_write_package as checker
import stage_hfs_stats_correction as correction
import write_trial_backups as backups
from hfs_read_results import frame_markers, parse_file

boot = correction.boot
ROOT = boot.ROOT
TOP_KEYS = frozenset(('fixture', 'baseline', 'reference', 'write_preflight', 'write_init',
                      'readonly_trial', 'linux_ready', 'correction_plan', 'correction_result', 'correction_inputs'))
READ_CHECKS = ['fresh_distinct_hfs_loader_sd_capacity_hfs_services_and_shell_ready', 'fresh_shell_nonce',
               'real_bsd_second_partition_node', 'cycle_1_directory_full_hashes_script_and_hfs_exec',
               'cycle_1_missing_read_recovery_nonforce_unmount_and_mount_gone',
               'cycle_2_directory_full_hashes_script_and_hfs_exec',
               'cycle_2_missing_read_recovery_nonforce_unmount_and_mount_gone',
               'shell_live_after_two_complete_hfs_mount_cycles']


def evidence_path(value):
    if not isinstance(value, str):
        raise ValueError('Expected explicit evidence filename')
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT / 'build/rpi5'):
        raise ValueError('Evidence must be an existing regular build/rpi5 file: ' + str(path))
    return path


def read_spec(path):
    spec = json.loads(path.read_text())
    if set(spec) != TOP_KEYS or not isinstance(spec['correction_inputs'], dict):
        raise ValueError('Incomplete explicit write-trial evidence bundle')
    paths = {key: evidence_path(value) for key, value in spec.items() if key != 'correction_inputs'}
    historical = {key: evidence_path(value) for key, value in spec['correction_inputs'].items()}
    required = {'fixture', 'baseline', 'reference', 'preflight', 'sd_trial', 'staging_plan', 'staging_result',
                'prior_plan', 'prior_result', 'prior_reference', 'prior_preflight', 'failed_state'}
    if historical.keys() != required:
        raise ValueError('Missing actual correction installation provenance')
    return paths, historical


def validate_read_trial(path, fixture, old_preflight, evidence):
    state = json.loads(path.read_text())
    raw_path = path.with_name('serial.bin')
    if raw_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Oversized RO acceptance capture')
    raw = raw_path.read_bytes()
    expected = dict(status='passed', mount_cycles_completed=2, sd_data_write_commands=0,
                    image_sha256=checker.HFS_READ_BASELINE_SHA256, partition='/dev/disk0s2', baud=115200)
    if (any(type(state.get(k)) is not type(v) or state[k] != v for k, v in expected.items())
            or state.get('checks') != READ_CHECKS or state.get('evidence_sha256') != evidence
            or old_preflight.get('image_sha256') != checker.HFS_READ_BASELINE_SHA256
            or state.get('bytes') != len(raw) or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or any(marker in raw for marker in boot.trial.ABORT_MARKERS)):
        raise ValueError('Prior physical two-cycle RO acceptance is not complete and bound')
    records = state.get('reads', [])
    entries = {entry['path']: entry for entry in fixture['files']}
    if len(records) != len(entries) * 2:
        raise ValueError('Incomplete RO full-file coverage')
    markers = [boot.trial.mount_marker(op, '/dev/disk0s2') for op in ('MOUNTED', 'STATUS', 'UNMOUNTED')]
    mounts = list(re.finditer(rb'(?m)^(' + b'|'.join(map(re.escape, markers)) + rb')\r{0,2}\n', raw))
    if [match[1] for match in mounts] != markers * 2:
        raise ValueError('RO mount/status/nonforce-unmount ordering is incomplete')
    nonces = [row.get('nonce') for row in records]
    if any(not isinstance(nonce, str) for nonce in nonces) or len(set(nonces)) != len(nonces):
        raise ValueError('Each RO file read must have its own nonce')
    # Startup diagnostics can contain torn CR bytes. Do not repair those or
    # run the strict FILE-response parser over unrelated startup chatter.
    # Extract only unique complete nonce lines, then strictly parse the entire
    # bounded raw frame (including every file byte/line ending).
    for cycle in (1, 2):
        selected = [row for row in records if type(row.get('mount_cycle')) is int and row['mount_cycle'] == cycle]
        if len(selected) != len(entries) or {row['path'] for row in selected} != set(entries):
            raise ValueError('Duplicate/missing RO fixture file')
        for row in selected:
            entry = entries[row['path']]
            begin, end = frame_markers(row['nonce'])
            starts = list(re.finditer(rb'(?m)^' + re.escape(begin) + rb'\r{0,2}\n', raw))
            stops = list(re.finditer(rb'(?m)^' + re.escape(end) + rb'\r{0,2}\n', raw))
            if len(starts) != 1 or len(stops) != 1:
                raise ValueError('Missing/duplicate RO raw full-file frame')
            start, stop = starts[0].start(), stops[0].start()
            if starts[0].end() > stop:
                raise ValueError('Reversed RO raw full-file frame')
            status, unmount = mounts[(cycle-1)*3+1:(cycle-1)*3+3]
            if not status.end() <= start < stops[0].end() <= unmount.start():
                raise ValueError('RO full-file frame is outside its mounted cycle')
            parsed = parse_file(raw[start:stops[0].end()], entry, row['nonce'])
            if any(row.get(key) != value for key, value in parsed.items()):
                raise ValueError('RO raw file bytes differ from acceptance record')
    return dict(state_sha256=checker.sha256(path), serial_sha256=hashlib.sha256(raw).hexdigest())


def load_plan(inputs, now=None):
    paths, historical = read_spec(inputs)
    snapshots = {key: checker.sha256(path) for key, path in paths.items()}
    historical_time = datetime.fromisoformat(json.loads(historical['reference'].read_text())['captured_at'])
    old = correction.load_plan(historical, now=historical_time)
    actual_plan = json.loads(paths['correction_plan'].read_text())
    if {key: value for key, value in actual_plan.items() if key != 'run'} != old:
        raise ValueError('Actual correction plan no longer binds its original evidence')
    old_result = json.loads(paths['correction_result'].read_text())
    validate_prior_correction(old_result, actual_plan)
    fixture = json.loads(paths['fixture'].read_text())
    baseline = json.loads(paths['baseline'].read_text())
    current = json.loads(paths['reference'].read_text())
    # Reuse the complete current reference/SD prerequisite checks with the
    # original immutable RO preflight, not a weaker invented success record.
    reports, hashes = boot.trial.load_inputs(dict(fixture=paths['fixture'], baseline=paths['baseline'],
        reference=paths['reference'], preflight=historical['preflight'], sd_trial=historical['sd_trial']), now=now)
    old_hashes = {key: actual_plan['evidence_sha256'][key] for key in ('fixture', 'baseline', 'reference', 'preflight', 'sd_trial')}
    physical = validate_read_trial(paths['readonly_trial'], fixture, reports['preflight'], old_hashes)
    saved = json.loads(paths['write_preflight'].read_text())
    build_path = Path(saved['kernel_build_manifest'])
    build = json.loads(build_path.read_text())
    kernel = Path(build['kernel_artifact']['path'])
    old_image = Path(reports['preflight']['image'])
    fresh = checker.inspect(Path(saved['image']).parent, kernel, paths['write_init'],
        ROOT / 'build/rpi5/bl33-probe-ci45m9zs/probe.bin', ROOT / 'build/rpi5/shell-userland-20261011/probe.bin',
        old_image, build_path)
    if saved != fresh or fresh.get('preflight_pass') is not True:
        raise ValueError('Write package preflight is changed/incomplete; rerun exact actual checks')
    ready = json.loads(paths['linux_ready'].read_text())
    identity = ready.get('identity', {})
    if (ready.get('status') != 'ready' or identity.get('root') != current['identity']['root']
            or identity.get('hostname') != 'kamidana'
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', identity.get('boot_id', ''))):
        raise ValueError('Exact SSD Linux readiness required')
    if any(checker.sha256(path) != snapshots[key] for key, path in paths.items()):
        raise ValueError('Write installation evidence changed during validation')
    stage = json.loads(historical['staging_result'].read_text())
    return dict(host=boot.HOST, expected=current['identity'], linux_boot_id=identity['boot_id'],
        fixture_sha256=fixture['image_sha256'], old_image_sha256=old_result['image_sha256'],
        new_image_sha256=fresh['image_sha256'], candidate=fresh['image'], profile='write-trial',
        backup_run=actual_plan['backup_run'], boot_backup_sha256=actual_plan['boot_backup_sha256'],
        original_mbr_sha256=actual_plan['original_mbr_sha256'], current_mbr_sha256=stage['mbr_after_sha256'],
        prior_boot_run=actual_plan['prior_boot_run'], prior_correction_run=actual_plan['run'],
        passed_sd_image_sha256=actual_plan['passed_sd_image_sha256'], failed_hfs_image_sha256=actual_plan['old_image_sha256'],
        evidence_sha256=snapshots, readonly_physical_acceptance=physical,
        historical_evidence_sha256={key: checker.sha256(path) for key, path in historical.items()},
        no_hfs_mount=True, no_partition_change=True, no_config_change=True, no_reboot=True)


def validate_prior_correction(result, plan):
    expected = dict(status='installed', run=plan['run'], image_sha256=checker.HFS_READ_BASELINE_SHA256,
        preserved_sd_image_sha256=plan['old_image_sha256'], sd_backup='probe.hfs-statfs-failed-20261012.bin',
        temporary_published=True, power_loss_atomicity_claimed=False, hfs_partition_unchanged=True,
        protected_boot_files_unchanged=True, boot_unmounted=True, no_hfs_mount=True,
        no_partition_change=True, no_config_change=True, no_reboot=True)
    if (plan.get('profile') != 'statfs-correction' or plan.get('new_image_sha256') != checker.HFS_READ_BASELINE_SHA256
            or not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-stats-[a-z0-9_]{8}', plan['run'])
            or any(type(result.get(k)) is not type(v) or result.get(k) != v for k, v in expected.items())):
        raise ValueError('Prior correction installation is not exact and complete')


def validate_result(result, plan):
    profile=plan.get('profile','write-trial')
    if profile not in ('write-trial','write-diagnostic','write-cache-diagnostic'):
        raise ValueError('Unknown write installation profile')
    expected = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
        preserved_sd_image_sha256=plan['old_image_sha256'], sd_backup=boot.core.INSTALL_NAMES[profile][0],
        temporary_published=True, power_loss_atomicity_claimed=False, hfs_partition_unchanged=True,
        protected_boot_files_unchanged=True, boot_unmounted=True, no_hfs_mount=True,
        no_partition_change=True, no_config_change=True, no_reboot=True)
    if any(type(result.get(k)) is not type(v) or result.get(k) != v for k, v in expected.items()):
        raise ValueError('Incomplete write-image installation; inspect existing run')
    saved = result.get('write_trial_backups', {})
    before = saved.get('before', [])
    after = saved.get('after', {})
    layout = (('/dev/mmcblk0', 512, 'mbr.before-write.bin'),
              ('/dev/mmcblk0p1', 536870912, 'boot-partition.before-write.img'),
              ('/dev/mmcblk0p2', 134217728, 'hfs-partition.before.img'))
    if (saved.get('linux_boot_id') != plan['linux_boot_id']
            or type(saved.get('sd_data_writes')) is not int or saved['sd_data_writes'] != 0
            or type(saved.get('hfs_mounts')) is not int or saved['hfs_mounts'] != 0
            or len(before) != 3 or set(after) != {'mbr', 'boot', 'hfs'}):
        raise ValueError('Incomplete full write-trial snapshots')
    for row, (node, size, name) in zip(before, layout):
        if (row.get('device') != node or type(row.get('bytes')) is not int or row['bytes'] != size
                or row.get('saved_as') != name or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', ''))):
            raise ValueError('Malformed full pre-write backup')
    for key, (node, size, _) in zip(('mbr', 'boot', 'hfs'), layout):
        row = after[key]
        if (row.get('device') != node or type(row.get('bytes')) is not int or row['bytes'] != size
                or row.get('saved_as') is not None or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', ''))):
            raise ValueError('Malformed post-install raw baseline')
    if (before[0]['sha256'] != plan['current_mbr_sha256'] or after['mbr']['sha256'] != plan['current_mbr_sha256']
            or before[2]['sha256'] != plan['fixture_sha256'] or after['hfs']['sha256'] != plan['fixture_sha256']
            or before[1]['sha256'] == after['boot']['sha256']):
        raise ValueError('Boot image not distinct or MBR/HFS changed')
    if profile in ('write-diagnostic','write-cache-diagnostic') and before[1]['sha256']!=plan['expected_boot_before_sha256']:
        raise ValueError('Historical full installed FAT baseline differs')


def remote_source(plan):
    profile=plan.get('profile','write-trial')
    if profile not in ('write-trial','write-diagnostic','write-cache-diagnostic'):
        raise ValueError('Unknown write installation profile')
    return ('INSTALL_PROFILE='+repr(profile)+'\n' + Path(backups.__file__).read_text() + '\n' + boot.remote_source(plan))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'build/rpi5'):
        parser.error('Use a fresh build/rpi5 output directory')
    return run_install(args.inputs,args.output,args.execute)


def run_install(inputs,output,execute,plan_loader=None):
    plan_loader=plan_loader or load_plan
    plan = plan_loader(inputs)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    if not execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(output))
        return 0
    if plan_loader(inputs) != plan:
        raise ValueError('Evidence changed before installation')
    prepare = boot.fixture_stage.PREPARE.replace("prefix='xnu-gate4-hfs-stage-'", "prefix='xnu-gate4-hfs-write-'")
    response = subprocess.run(boot.SSH + ['python3 -'], input=prepare, text=True, capture_output=True, check=True, timeout=30)
    run = json.loads(response.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-write-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected write-trial NVMe directory')
    plan['run'] = run
    (output / 'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    plan['candidate'], boot.HOST + ':' + run + '/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response = subprocess.run(boot.SSH + ['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, value in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (output / name).write_bytes(value.encode() if isinstance(value, str) else value or b'')
        (output / 'outcome-unknown.txt').write_text('Inspect existing remote run; never automatically retry/rollback.\n')
        raise
    (output / 'remote.stdout').write_text(response.stdout)
    (output / 'remote.stderr').write_text(response.stderr)
    response.check_returncode()
    result = json.loads(response.stdout)
    validate_result(result, plan)
    (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
