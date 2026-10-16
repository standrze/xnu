# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic chain/log mutations only; not physical Gate 4 acceptance."""
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_hfs_persistence as check
from tools.rpi5.tests import test_hfs_persistence_capture as fixtures


NOW = datetime(2026, 10, 12, 6, tzinfo=timezone.utc)


class MacLogAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.audit = self.root / 'audit'; self.audit.mkdir()
        self.image = self.root / 'capture.raw'; self.mount = self.audit / 'readonly-mount'
        self.plan = dict(image=str(self.image), image_sha256='1' * 64, fixture=str(self.root / 'fixture.json'), fixture_files=[])
        sources = {Path(check.mac.__file__).resolve(), Path(check.mac.own_attachment.__code__.co_filename).resolve(),
                   Path(check.mac.verify_files.__code__.co_filename).resolve(), Path(check.mac.validate_entry.__code__.co_filename).resolve()}
        self.record = dict(status='local_image_audit_passed', plan=self.plan, detach_count=2, durability_verified=False,
            readonly_fsck_verified=True, readonly_remount_verified=True, image_unchanged=True, mac_attachment_detached=True,
            fixture_files=[], write_files=check.mac.expected_entries(), started_at='2026-10-12T04:10:00+00:00',
            finished_at='2026-10-12T04:11:00+00:00', source_inputs_sha256={str(p): check.mac.digest(p) for p in sorted(sources)}, commands=[])
        volume = plistlib.dumps(dict(FilesystemType='hfs', VolumeName=check.mac.VOLUME, MountPoint=str(self.mount), DeviceNode='/dev/disk124'))
        def info(device=None, mounted=False):
            if not device: return plistlib.dumps({'images': []})
            entity = {'dev-entry': device, 'content-hint': ''}
            if mounted: entity['mount-point'] = str(self.mount)
            return plistlib.dumps({'images': [{'image-path': str(self.image), 'writeable': False, 'blocksize': 512,
                'blockcount': check.mac.IMAGE_BYTES // 512, 'image-encrypted': False, 'system-entities': [entity]}]})
        rows = [
            (['hdiutil', 'info', '-plist'], info()),
            (['hdiutil', 'attach', str(self.image), '-readonly', '-nobrowse', '-noautoopen', '-noautofsck', '-nomount', '-plist'], b'attach'),
            (['hdiutil', 'info', '-plist'], info('/dev/disk123')),
            (['/sbin/fsck_hfs', '-fn', '/dev/disk123'], b'fsck modeled OK'),
            (['hdiutil', 'info', '-plist'], info('/dev/disk123')),
            (['hdiutil', 'detach', '/dev/disk123'], b'detach'),
            (['hdiutil', 'info', '-plist'], info()),
            (['hdiutil', 'attach', str(self.image), '-readonly', '-nobrowse', '-noautoopen', '-noautofsck', '-mountpoint', str(self.mount), '-plist'], b'attach'),
            (['hdiutil', 'info', '-plist'], info('/dev/disk124', True)),
            (['diskutil', 'info', '-plist', str(self.mount)], volume),
            (['diskutil', 'info', '-plist', str(self.mount)], volume),
            (['hdiutil', 'info', '-plist'], info('/dev/disk124', True)),
            (['hdiutil', 'info', '-plist'], info('/dev/disk124', True)),
            (['hdiutil', 'detach', '/dev/disk124'], b'detach'),
            (['hdiutil', 'info', '-plist'], info())]
        for index, (argv, stdout) in enumerate(rows, 1):
            (self.audit / f'command-{index}.stdout').write_bytes(stdout)
            (self.audit / f'command-{index}.stderr').write_bytes(b'')
            self.record['commands'].append(dict(argv=argv, status='complete', returncode=0,
                stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(b'').hexdigest()))
        (self.audit / 'volume-info.plist').write_bytes(volume)
        (self.audit / 'plan.json').write_text(json.dumps(self.plan)); self.save()

    def save(self):
        (self.audit / 'result.json').write_text(json.dumps(self.record))

    def verify(self):
        with patch.object(check, 'evidence', side_effect=Path), patch.object(check.mac, 'plan', return_value=self.plan):
            return check.validate_mac(self.audit, self.plan, now=NOW)

    def test_all_15_commands_outputs_ownership_and_file_vector_records_are_bound(self):
        self.assertEqual(self.verify()['status'], 'local_image_audit_passed')
        self.assertIs(self.verify()['durability_verified'], False)

    def test_repair_rw_force_other_targets_failure_missing_files_or_changed_source_are_refused(self):
        original = copy.deepcopy(self.record)
        for fault in ('repair', 'rw', 'force', 'target', 'exit', 'exit-bool', 'unknown', 'count', 'files', 'source', 'time', 'plan'):
            self.record = copy.deepcopy(original)
            if fault == 'repair': self.record['commands'][3]['argv'][1] = '-fy'
            if fault == 'rw': self.record['commands'][7]['argv'].remove('-readonly')
            if fault == 'force': self.record['commands'][13]['argv'].append('-force')
            if fault == 'target': self.record['commands'][3]['argv'][-1] = '/dev/disk0'
            if fault == 'exit': self.record['commands'][3]['returncode'] = 8
            if fault == 'exit-bool': self.record['commands'][3]['returncode'] = False
            if fault == 'unknown': self.record['commands'][3]['status'] = 'unknown'
            if fault == 'count': self.record['commands'].pop()
            if fault == 'files': self.record['write_files'].pop()
            if fault == 'source': self.record['source_inputs_sha256'] = {}
            if fault == 'time': self.record['finished_at'] = self.record['started_at']
            if fault == 'plan': self.record['plan']['image_sha256'] = '0' * 64
            self.save()
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.verify()

    def test_even_rehashed_logs_cannot_hide_writable_ambiguous_missing_or_wrong_geometry_attachment(self):
        file = self.audit / 'command-3.stdout'; original = file.read_bytes()
        for fault in ('writable', 'ambiguous', 'missing', 'geometry', 'mounted', 'partition'):
            data = plistlib.loads(original); row = data['images'][0]
            if fault == 'writable': row['writeable'] = True
            if fault == 'ambiguous': data['images'].append(copy.deepcopy(row))
            if fault == 'missing': data['images'] = []
            if fault == 'geometry': row['blockcount'] += 1
            if fault == 'mounted': row['system-entities'][0]['mount-point'] = str(self.mount)
            if fault == 'partition': row['system-entities'][0]['dev-entry'] += 's1'
            file.write_bytes(plistlib.dumps(data)); self.record['commands'][2]['stdout_sha256'] = check.mac.digest(file); self.save()
            with self.subTest(fault=fault), self.assertRaises(ValueError): self.verify()

    def test_changed_raw_logs_volume_info_or_image_plan_fail(self):
        file = self.audit / 'command-4.stdout'; file.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.verify()
        file.write_bytes(b'fsck modeled OK')
        (self.audit / 'volume-info.plist').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.verify()


class PersistenceChainTests(unittest.TestCase):
    def test_complete_snapshot_includes_every_log_image_and_trial_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); installed = root / 'installed'; cap = root / 'capture'; audit = root / 'audit'
            for path in (installed, cap, audit): path.mkdir()
            paths = [root / 'inputs.json', root / 'state.json', root / 'serial.bin',
                *[installed / name for name in ('plan.json', 'result.json', 'remote-source.sha256')],
                *[cap / name for name in ('plan.json', 'remote-source.sha256', 'remote-result.json', 'remote.stdout',
                                         'remote.stderr', 'capture.json', check.capture.core.IMAGE_NAME)],
                *[audit / name for name in ('plan.json', 'result.json', 'volume-info.plist')],
                *[audit / f'command-{index}.{stream}' for index in range(1, 16) for stream in ('stdout', 'stderr')]]
            for path in paths: path.write_bytes(b'original')
            with patch.object(check, 'evidence', side_effect=Path):
                before = check.artifact_snapshots(root / 'inputs.json', installed, root / 'state.json', cap, audit)
                self.assertEqual(len(before), len(paths) + 1) # Also the checker source itself.
                (audit / 'command-4.stdout').write_bytes(b'changed')
                after = check.artifact_snapshots(root / 'inputs.json', installed, root / 'state.json', cap, audit)
            self.assertNotEqual(before, after)
            self.assertNotEqual(before[str(audit / 'command-4.stdout')], after[str(audit / 'command-4.stdout')])

    def bundle(self, root):
        capture_dir = root / 'capture'; capture_dir.mkdir(); audit_dir = root / 'audit'; audit_dir.mkdir()
        plan, remote = fixtures.plan_and_report()
        plan['linux_verified_utc'] = '2026-10-12T04:07:00+00:00'
        plan['write_trial_ended_utc'] = '2026-10-12T04:05:00+00:00'
        plan['trial_state_sha256'] = 'e' * 64
        plan['write_installation_sha256'] = {'actual': 'modeled'}
        baseline = {key: value for key, value in plan.items() if key not in ('run', 'linux_boot_id_after_write', 'linux_verified_utc')}
        source = check.capture.remote_source(plan); source_sha = hashlib.sha256(source.encode()).hexdigest()
        (capture_dir / 'plan.json').write_text(json.dumps(plan))
        (capture_dir / 'remote-source.sha256').write_text(source_sha + '\n')
        (capture_dir / 'remote-result.json').write_text(json.dumps(remote))
        (capture_dir / 'remote.stdout').write_text(json.dumps(remote))
        image = capture_dir / check.capture.core.IMAGE_NAME; image.write_bytes(b'captured')
        fixture = root / 'fixture.json'; fixture.write_text(json.dumps({'image_sha256': plan['fixture_sha256']}))
        inputs = root / 'inputs.json'; inputs.write_text(json.dumps({'fixture': str(fixture)}))
        report = dict(remote, local_image=str(image), volume_header={'modeled': True},
            plan_sha256=check.mac.digest(capture_dir / 'plan.json'), captured_utc='2026-10-12T04:08:00+00:00',
            capture_source_sha256=check.mac.digest(Path(check.capture.__file__)), remote_source_sha256=source_sha)
        (capture_dir / 'capture.json').write_text(json.dumps(report)); (audit_dir / 'result.json').write_text('{}')
        expected_mac = dict(image=str(image), image_sha256=report['image_sha256'], fixture=str(fixture),
                            volume_header=report['volume_header'])
        audit = dict(started_at='2026-10-12T04:10:00+00:00')
        return capture_dir, audit_dir, baseline, plan, report, inputs, expected_mac, audit

    def inspect(self, data):
        capture_dir, audit_dir, baseline, plan, report, inputs, expected_mac, audit = data
        with patch.object(check, 'evidence', side_effect=Path), patch.object(check.capture, 'load_plan', return_value=baseline), \
                patch.object(check.mac, 'plan', return_value=expected_mac), patch.object(check, 'validate_mac', return_value=audit), \
                patch.object(check, 'artifact_snapshots', return_value={'modeled': 'hash'}):
            return check.inspect(inputs, Path('installed'), Path('trial'), capture_dir, audit_dir, now=NOW)

    def test_complete_chain_binds_admitted_trial_new_boot_capture_and_later_mac_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.inspect(self.bundle(Path(directory).resolve()))
            self.assertEqual(result['status'], 'physical_hfs_persistence_verified')
            self.assertIs(result['durability_verified'], True)
            self.assertEqual(result['evidence_sha256'], {'modeled': 'hash'})
            self.assertNotEqual(result['linux_boot_id_before_write'], result['linux_boot_id_after_write'])

    def test_mismatched_or_chronologically_unrelated_components_cannot_prove_persistence(self):
        for fault in ('plan', 'source', 'stdout', 'report-source', 'protected', 'time', 'early-audit', 'other-image', 'fixture'):
            with tempfile.TemporaryDirectory() as directory:
                data = self.bundle(Path(directory).resolve()); cap, aud, base, plan, report, inputs, macplan, audit = data
                if fault == 'plan': base['fixture_sha256'] = '0' * 64
                if fault == 'source': (cap / 'remote-source.sha256').write_text('0' * 64)
                if fault == 'stdout': (cap / 'remote.stdout').write_text('{}')
                if fault == 'report-source': report['capture_source_sha256'] = '0' * 64
                if fault == 'protected': report['protected']['boot']['sha256'] = '0' * 64
                if fault == 'time': report['captured_utc'] = '2026-10-12T04:04:00+00:00'
                if fault == 'early-audit': audit['started_at'] = '2026-10-12T04:06:00+00:00'
                if fault == 'other-image': report['local_image'] = str(cap / 'different.raw'); (cap / 'different.raw').write_bytes(b'captured')
                if fault == 'fixture': (Path(directory) / 'fixture.json').write_text(json.dumps({'image_sha256': '0' * 64}))
                (cap / 'capture.json').write_text(json.dumps(report))
                with self.subTest(fault=fault), self.assertRaises(ValueError): self.inspect(data)

    def test_failed_physical_trial_prevents_output_and_mac_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'acceptance.json'
            argv = ['check.py', '--inputs', 'inputs', '--installed', 'installed', '--trial', 'trial',
                    '--capture', 'capture', '--audit', 'audit', '--output', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(check.mac, 'owned_path', side_effect=Path), \
                    patch.object(check.capture, 'load_plan', side_effect=ValueError('zero-input failed trial')), \
                    patch.object(check, 'validate_mac') as mac, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                check.main()
            self.assertFalse(output.exists()); mac.assert_not_called()


if __name__ == '__main__': unittest.main()
