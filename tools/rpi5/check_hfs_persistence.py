#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bind actual write/new-boot/raw-capture/Mac fsck/RO file proof, read-only.

No network, serial, mount, device access or repair. Never marks a goal complete.
This verifies the persistence portion of Gate 4, not unrelated gate criteria.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re

import audit_hfs_persistence_image as mac
import capture_hfs_persistence as capture


def evidence(path):
    return capture.installer.evidence_path(str(path))


def artifact_snapshots(inputs, installed, trial, capture_dir, audit_dir):
    paths = [inputs, trial, Path(trial).with_name('serial.bin'), Path(__file__),
             *[installed / name for name in ('plan.json', 'result.json', 'remote-source.sha256')],
             *[capture_dir / name for name in ('plan.json', 'remote-source.sha256', 'remote-result.json',
                                               'remote.stdout', 'remote.stderr', 'capture.json', capture.core.IMAGE_NAME)],
             *[audit_dir / name for name in ('plan.json', 'result.json', 'volume-info.plist')],
             *[audit_dir / f'command-{index}.{stream}' for index in range(1, 16) for stream in ('stdout', 'stderr')]]
    result = {}
    for path in paths:
        # Script code is repository-owned; evidence artifacts must stay in build.
        path = Path(path).resolve() if Path(path) == Path(__file__) else evidence(path)
        result[str(path)] = mac.digest(path)
    return result


def command_artifacts(directory, commands):
    outputs = []
    if len(commands) != 15:
        raise ValueError('Require exactly the successful two-attachment Mac command sequence')
    for index, row in enumerate(commands, 1):
        if row.get('status') != 'complete' or type(row.get('returncode')) is not int or row['returncode'] != 0:
            raise ValueError('Mac command failed, incomplete or outcome unknown')
        files = [evidence(directory / f'command-{index}.{stream}') for stream in ('stdout', 'stderr')]
        if any(path.stat().st_size > 16 * 1024 * 1024 for path in files):
            raise ValueError('Oversized Mac audit log')
        data = [path.read_bytes() for path in files]
        if any(hashlib.sha256(value).hexdigest() != row.get(stream + '_sha256')
               for stream, value in zip(('stdout', 'stderr'), data)):
            raise ValueError('Mac command output bytes differ from recorded hashes')
        outputs.append(data[0])
    return outputs


def validate_mac(directory, expected_plan, now=None):
    """Recheck real captured logs/ownership/command flags, not success booleans."""
    record = json.loads(evidence(directory / 'result.json').read_text())
    saved_plan = json.loads(evidence(directory / 'plan.json').read_text())
    if saved_plan != expected_plan or record.get('plan') != expected_plan:
        raise ValueError('Mac audit is not bound to the actual captured image/fixture')
    expected = dict(status='local_image_audit_passed', detach_count=2, durability_verified=False,
                    readonly_fsck_verified=True, readonly_remount_verified=True,
                    image_unchanged=True, mac_attachment_detached=True)
    if any(type(record.get(key)) is not type(value) or record[key] != value for key, value in expected.items()):
        raise ValueError('Incomplete Mac fsck/RO remount/detach/image checks')
    sources = {Path(mac.__file__).resolve(), Path(mac.own_attachment.__code__.co_filename).resolve(),
               Path(mac.verify_files.__code__.co_filename).resolve(), Path(mac.validate_entry.__code__.co_filename).resolve()}
    if record.get('source_inputs_sha256') != {str(path): mac.digest(path) for path in sorted(sources)}:
        raise ValueError('Mac auditor/helper source changed since execution')
    if record.get('fixture_files') != expected_plan['fixture_files'] or record.get('write_files') != mac.expected_entries():
        raise ValueError('Mac audit is missing original or written complete file coverage')
    started, finished = capture.timestamp(record['started_at']), capture.timestamp(record['finished_at'])
    if not started < finished <= (now or datetime.now(timezone.utc)):
        raise ValueError('Invalid Mac audit chronology')
    commands = record.get('commands', []); output = command_artifacts(directory, commands)
    info = {index: plistlib.loads(output[index]) for index in (0, 2, 4, 6, 8, 11, 12, 14)}
    image, mount = Path(expected_plan['image']), directory / 'readonly-mount'
    for index in (0, 6, 14):
        if mac.image_rows(info[index], image): raise ValueError('Image pre-existed or was not detached')
    unmounted = mac.own_attachment(info[2], image)
    if mac.own_attachment(info[4], image) != unmounted: raise ValueError('Fsck attachment ownership changed')
    mounted = mac.own_attachment(info[8], image, mount)
    if any(mac.own_attachment(info[index], image, mount) != mounted for index in (11, 12)):
        raise ValueError('Read-only remount ownership changed')
    expected_commands = [
        ['hdiutil', 'info', '-plist'],
        ['hdiutil', 'attach', str(image), '-readonly', '-nobrowse', '-noautoopen', '-noautofsck', '-nomount', '-plist'],
        ['hdiutil', 'info', '-plist'], ['/sbin/fsck_hfs', '-fn', unmounted],
        ['hdiutil', 'info', '-plist'], ['hdiutil', 'detach', unmounted], ['hdiutil', 'info', '-plist'],
        ['hdiutil', 'attach', str(image), '-readonly', '-nobrowse', '-noautoopen', '-noautofsck', '-mountpoint', str(mount), '-plist'],
        ['hdiutil', 'info', '-plist'], ['diskutil', 'info', '-plist', str(mount)],
        ['diskutil', 'info', '-plist', str(mount)], ['hdiutil', 'info', '-plist'], ['hdiutil', 'info', '-plist'],
        ['hdiutil', 'detach', mounted], ['hdiutil', 'info', '-plist']]
    if [row.get('argv') for row in commands] != expected_commands:
        raise ValueError('Mac audit command sequence/targets/repair/read-only flags differ')
    for index in (9, 10):
        volume = plistlib.loads(output[index])
        if (volume.get('FilesystemType') != 'hfs' or volume.get('VolumeName') != mac.VOLUME or
                volume.get('MountPoint') != str(mount) or volume.get('DeviceNode') != mounted):
            raise ValueError('Recorded remount device/filesystem differs')
    if evidence(directory / 'volume-info.plist').read_bytes() != output[9]:
        raise ValueError('Independent volume-info artifact differs from the actual command output')
    if mac.plan(image, expected_plan['image_sha256'], Path(expected_plan['fixture'])) != expected_plan:
        raise ValueError('Complete image/header/fixture differs since the Mac audit')
    return record


def inspect(inputs, installed, trial, capture_dir, audit_dir, now=None):
    now = now or datetime.now(timezone.utc)
    baseline = capture.load_plan(inputs, installed, trial, now=now)
    snapshots = artifact_snapshots(inputs, installed, trial, capture_dir, audit_dir)
    plan_path = evidence(capture_dir / 'plan.json'); plan = json.loads(plan_path.read_text())
    extras = {'run', 'linux_boot_id_after_write', 'linux_verified_utc'}
    if {key: value for key, value in plan.items() if key not in extras} != baseline or not extras <= plan.keys():
        raise ValueError('Actual capture plan differs from the admitted physical write evidence')
    source = capture.remote_source(plan); source_sha = hashlib.sha256(source.encode()).hexdigest()
    if evidence(capture_dir / 'remote-source.sha256').read_text().strip() != source_sha:
        raise ValueError('Executed remote capture source differs')
    report_path = evidence(capture_dir / 'capture.json'); report = json.loads(report_path.read_text())
    remote = json.loads(evidence(capture_dir / 'remote-result.json').read_text())
    if json.loads(evidence(capture_dir / 'remote.stdout').read_text()) != remote:
        raise ValueError('Original capture stdout differs from its result')
    extra_report = {'local_image', 'volume_header', 'plan_sha256', 'captured_utc', 'capture_source_sha256', 'remote_source_sha256'}
    if ({key: value for key, value in report.items() if key not in extra_report} != remote or
            not extra_report <= report.keys() or report['plan_sha256'] != mac.digest(plan_path) or
            report['capture_source_sha256'] != mac.digest(Path(capture.__file__)) or
            report['remote_source_sha256'] != source_sha):
        raise ValueError('Capture result source/provenance differs')
    capture.validate_report(remote, plan); capture.validate_report(report, plan)
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', plan['linux_boot_id_after_write']):
        raise ValueError('Actual new Linux boot ID is invalid')
    ended, verified, captured = map(capture.timestamp, (baseline['write_trial_ended_utc'], plan['linux_verified_utc'], report['captured_utc']))
    if not ended <= verified <= captured <= now: raise ValueError('Write/new-Linux/capture chronology differs')
    image = evidence(report['local_image'])
    if image != (capture_dir / capture.core.IMAGE_NAME).absolute():
        raise ValueError('Local capture is not its own exact immutable artifact')
    inputs_spec = json.loads(evidence(inputs).read_text())
    if 'current_inputs' in inputs_spec:
        inputs_spec = json.loads(evidence(inputs_spec['current_inputs']).read_text())
    fixture = evidence(inputs_spec['fixture'])
    fixture_record = json.loads(fixture.read_text())
    if fixture_record['image_sha256'] != baseline['fixture_sha256']:
        raise ValueError('Capture original fixture provenance differs')
    expected_mac = mac.plan(image, report['image_sha256'], fixture)
    if expected_mac['volume_header'] != report['volume_header']:
        raise ValueError('Captured HFS header differs before/after read-only audit')
    audit = validate_mac(audit_dir, expected_mac, now=now)
    if capture.timestamp(audit['started_at']) < captured:
        raise ValueError('Mac audit predates actual post-reboot partition capture')
    if (capture.load_plan(inputs, installed, trial, now=now) != baseline or
            artifact_snapshots(inputs, installed, trial, capture_dir, audit_dir) != snapshots):
        raise ValueError('Physical capture/audit evidence changed during final validation')
    return dict(status='physical_hfs_persistence_verified', durability_verified=True,
        verified_utc=now.isoformat(), linux_boot_id_before_write=plan['linux_boot_id_before_write'],
        linux_boot_id_after_write=plan['linux_boot_id_after_write'], image_sha256=report['image_sha256'],
        protected_mbr_sha256=plan['mbr_sha256'], protected_full_fat_sha256=plan['boot_sha256'],
        write_trial_state_sha256=baseline['trial_state_sha256'], capture_sha256=mac.digest(report_path),
        mac_audit_sha256=mac.digest(evidence(audit_dir / 'result.json')),
        write_installation_sha256=baseline['write_installation_sha256'], evidence_sha256=snapshots,
        scope='Actual one-batch HFS persistence across reboot, no-repair fsck, RO full-ten-file readback and protected boot bytes; no DMA or unrelated gate claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'installed', 'trial', 'capture', 'audit', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    output = mac.owned_path(args.output)
    if output.exists(): raise ValueError('Preserve prior acceptance evidence; use a fresh output')
    result = inspect(args.inputs, args.installed, args.trial, args.capture.absolute(), args.audit.absolute())
    with output.open('x') as stream: stream.write(json.dumps(result, indent=2) + '\n')
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
