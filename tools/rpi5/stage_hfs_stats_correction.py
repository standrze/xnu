#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct correction for the observed pre-mount mockfs statfs failure only.

Local-only by default. Never partitions, mounts HFS, changes configuration,
reboots, overwrites backups, retries an unknown outcome or enables SD writes.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

import stage_hfs_boot as boot
from check_hfs_stats_package import linked_getter
from audit_macho import inspect as inspect_macho

KEYS = ('fixture', 'baseline', 'reference', 'preflight', 'sd_trial', 'staging_plan', 'staging_result')


def validate_installed(result, plan):
    required = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
                    preserved_sd_image_sha256=plan['old_image_sha256'], hfs_partition_unchanged=True,
                    protected_boot_files_unchanged=True, boot_unmounted=True, no_hfs_mount=True,
                    no_partition_change=True, no_config_change=True, no_reboot=True,
                    sd_backup='probe.sd-read-passed-20261012.bin', temporary_published=True,
                    power_loss_atomicity_claimed=False)
    if (any(type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in required.items()) or
            not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-boot-[a-z0-9_]{8}', plan['run'])):
        raise ValueError('Prior initial HFS boot installation is not complete and bound')


def validate_failure(path, reports, hashes):
    saved = path.read_bytes()
    state = json.loads(saved)
    raw_path = path.parent / 'serial.bin'
    if raw_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Oversized failed HFS capture')
    raw = raw_path.read_bytes()
    checks = ['fresh_repeated_shell_readiness_after_explicit_capture_gap',
              'fresh_distinct_hfs_loader_sd_capacity_hfs_services_and_shell_ready',
              'fresh_shell_nonce', 'real_bsd_second_partition_node']
    if (state.get('status') != 'failed' or state.get('error') != 'shell command did not complete: hfsro mount /dev/disk0s2'
            or state.get('checks') != checks or state.get('reads') != []
            or type(state.get('mount_cycles_completed')) is not int or state['mount_cycles_completed'] != 0
            or type(state.get('sd_data_write_commands')) is not int or state['sd_data_write_commands'] != 0
            or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != 56
            or state.get('image_sha256') != reports['preflight']['image_sha256']
            or state.get('evidence_sha256') != hashes or state.get('partition') != '/dev/disk0s2'
            or state.get('device') != '/dev/cu.usbmodem102' or state.get('baud') != 115200
            or state.get('bytes') != len(raw) or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or any(marker in raw for marker in (*boot.trial.ABORT_MARKERS, b'RPI5XNU:HFSRO:'))):
        raise ValueError('Not the preserved failed pre-mount statfs trial')
    # Boot chatter includes the already-recorded torn encoder banner. Inspect
    # only the intact command response, without repairing any boot bytes.
    echo = b'xnu:/# hfsro mount /dev/disk0s2'
    if raw.count(echo) != 1 or raw.count(b'hfsro mount /dev/disk0s2') != 1:
        raise ValueError('Missing or repeated mount command echo')
    start = raw.index(echo)
    end = raw.find(b'xnu:/#', start + len(echo))
    if end == -1 or end - start > 4096:
        raise ValueError('Missing bounded completed pre-mount response')
    normalized = boot.trial.normalize_output(raw[start:end + len(b'xnu:/#')])
    response = b'xnu:/# hfsro mount /dev/disk0s2\nhfsro statfs64: errno 45\nxnu:/#'
    if normalized != response:
        raise ValueError('Raw capture lacks the unique completed pre-mount ENOTSUP response')
    # Validate the original zero-input prefix at the actual continuation time,
    # not as permission to resume today. The subsequent trial is a fresh boot.
    original = Path(state['continuation_of'])
    prior_raw, prior_metadata = boot.trial.load_zero_tx_resume(
        original, reports, hashes, state['device'], state['partition'],
        now=datetime.fromisoformat(state['started_utc']))
    # load_zero_tx_resume returns its complete original bytes and metadata.
    if not raw.startswith(prior_raw):
        raise ValueError('Failed continuation does not preserve original boot bytes')
    if (any(state.get(key) != value for key, value in prior_metadata.items())
            or state.get('previous_state_sha256') != boot.trial.sha256(original)
            or state.get('previous_raw_sha256') != boot.trial.sha256(original.parent / 'serial.bin')
            or state.get('capture_segments') != 2 or state.get('closed_port_interval_observed') is not False):
        raise ValueError('Failed continuation provenance differs')
    return dict(failed_state=hashlib.sha256(saved).hexdigest(), failed_serial=hashlib.sha256(raw).hexdigest(),
                original_state=boot.trial.sha256(original), original_serial=boot.trial.sha256(original.parent / 'serial.bin'))


def load_plan(paths, now=None):
    current_paths = {key: paths[key] for key in KEYS}
    snapshots = {key: path.read_bytes() for key, path in paths.items()}
    current = boot.load_plan(current_paths, now=now)  # CLI always uses actual current time.
    historical_paths = dict(current_paths, reference=paths['prior_reference'], preflight=paths['prior_preflight'])
    captured = datetime.fromisoformat(json.loads(paths['prior_reference'].read_text())['captured_at'])
    historical = boot.load_plan(historical_paths, now=captured)
    prior_plan_raw, prior_result_raw = paths['prior_plan'].read_bytes(), paths['prior_result'].read_bytes()
    prior_plan, prior_result = json.loads(prior_plan_raw), json.loads(prior_result_raw)
    if {key: value for key, value in prior_plan.items() if key != 'run'} != historical:
        raise ValueError('Prior installer plan no longer binds its original physical evidence')
    validate_installed(prior_result, prior_plan)
    reports, hashes = boot.trial.load_inputs({key: historical_paths[key] for key in KEYS[:5]}, now=captured)
    failure = validate_failure(paths['failed_state'], reports, hashes)
    report = json.loads(paths['preflight'].read_text())
    build = json.loads(Path(report['kernel_build_manifest']).read_text())
    # The successful build manifest records the exact output; no symbol-name-only claim.
    kernel = Path(build['output_root']) / 'obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712'
    raw = kernel.read_bytes()
    wiring = linked_getter(raw, inspect_macho(raw)['segments'],
                           subprocess.check_output(['xcrun', 'nm', '-nm', str(kernel)], text=True),
                           (boot.ROOT / 'bsd/sys/mount.h').read_text())
    if (report.get('hfs_ramroot_stats_trial') is not True or
            report['checks'].get('ramroot_statfs_getter_wired') is not True or
            report.get('linked_ramroot_statfs') != wiring or
            hashlib.sha256(raw).hexdigest() != report['kernel_sha256'] or
            report['init_sha256'] != reports['preflight']['init_sha256'] or
            current['new_image_sha256'] in (historical['old_image_sha256'], historical['new_image_sha256'])
            or current['expected'] != historical['expected']):
        raise ValueError('Correction is not the separately linked stats fix with unchanged read-only userland/card')
    evidence = {key: boot.trial.sha256(path) for key, path in paths.items()}
    if any(evidence[key] != hashlib.sha256(raw).hexdigest() for key, raw in snapshots.items()):
        raise ValueError('Corrective evidence changed during validation')
    current.update(old_image_sha256=historical['new_image_sha256'],
                   passed_sd_image_sha256=historical['old_image_sha256'], prior_boot_run=prior_plan['run'],
                   profile='statfs-correction', failure_evidence_sha256=failure, evidence_sha256=evidence)
    return current


def remote_source(plan):
    return 'INSTALL_PROFILE="statfs-correction"\n' + boot.remote_source(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = dict(fixture='fixture', baseline='sd-baseline-reference', reference='reference', preflight='preflight',
                 sd_trial='sd-trial', staging_plan='staging-plan', staging_result='staging-result',
                 prior_plan='prior-plan', prior_result='prior-result', prior_reference='prior-reference',
                 prior_preflight='prior-preflight', failed_state='failed-state')
    for flag in (*flags.values(), 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((boot.ROOT / 'build/rpi5').resolve()):
        parser.error('Use a fresh build/rpi5 output directory')
    paths = {key: getattr(args, flag.replace('-', '_')) for key, flag in flags.items()}
    plan = load_plan(paths)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(args.output))
        return 0
    if load_plan(paths) != plan:
        raise ValueError('Corrective installation evidence changed before execution')
    prepare = boot.fixture_stage.PREPARE.replace("prefix='xnu-gate4-hfs-stage-'", "prefix='xnu-gate4-hfs-stats-'")
    response = subprocess.run(boot.SSH + ['python3 -'], input=prepare, text=True, capture_output=True, check=True, timeout=30)
    run = json.loads(response.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-stats-[a-z0-9_]{8}', run):
        raise ValueError('Unexpected corrective NVMe directory')
    plan['run'] = run
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    plan['candidate'], boot.HOST + ':' + run + '/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (args.output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        response = subprocess.run(boot.SSH + ['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, data in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (args.output / name).write_bytes(data.encode() if isinstance(data, str) else data or b'')
        (args.output / 'outcome-unknown.txt').write_text('Inspect the existing remote run; never retry or roll back automatically.\n')
        raise
    (args.output / 'remote.stdout').write_text(response.stdout)
    (args.output / 'remote.stderr').write_text(response.stderr)
    response.check_returncode()
    result = json.loads(response.stdout)
    expected = dict(status='installed', run=run, image_sha256=plan['new_image_sha256'],
                    preserved_sd_image_sha256=plan['old_image_sha256'], sd_backup=boot.core.INSTALL_NAMES['statfs-correction'][0],
                    hfs_partition_unchanged=True, protected_boot_files_unchanged=True, boot_unmounted=True,
                    no_hfs_mount=True, no_partition_change=True, no_config_change=True, no_reboot=True,
                    temporary_published=True, power_loss_atomicity_claimed=False)
    if any(type(result.get(key)) is not type(value) or result.get(key) != value for key, value in expected.items()):
        raise ValueError('Incomplete corrective install; inspect existing run')
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
