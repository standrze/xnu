# SPDX-License-Identifier: BSD-2-Clause
"""Modeled Mac commands + real temporary file reads; not hardware durability."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.rpi5 import audit_hfs_persistence_image as audit
from tools.rpi5 import hfs_write_results
from tools.rpi5.tests.test_hfs_fixture import header


def original_files(root):
    entries = []
    for index, name in enumerate(sorted(audit.FILE_PATHS)):
        data = b'' if name.endswith('/empty') else bytes(range(256)) * (index + 1)
        target = root / name.lstrip('/')
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        mode = 0o555 if name == '/bin/echo' else 0o444
        target.chmod(mode)
        entries.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), mode=mode))
    return entries


class PersistenceFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.entries = original_files(self.root)

    def test_all_original_files_full_read_twice(self):
        self.assertEqual(audit.verify_fixture_files(self.root, self.entries), self.entries)

    def test_corruption_length_permissions_links_and_symlink_parent_refused(self):
        for fault in ('bytes', 'length', 'mode', 'hardlink', 'leaf-link', 'parent-link'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); entries = original_files(root)
                file = root / 'etc/proof.txt'
                if fault in ('bytes', 'length'):
                    file.chmod(0o644)
                    file.write_bytes(b'x' * file.stat().st_size if fault == 'bytes' else file.read_bytes() + b'x')
                    file.chmod(0o444)
                if fault == 'mode': file.chmod(0o644)
                if fault == 'hardlink': os.link(file, root / 'extra-link')
                if fault == 'leaf-link': file.unlink(); file.symlink_to(root / 'etc/cross-page.bin')
                if fault == 'parent-link': (root / 'etc').rename(root / 'real-etc'); (root / 'etc').symlink_to(root / 'real-etc')
                with self.subTest(fault=fault), self.assertRaises((ValueError, OSError)):
                    audit.verify_fixture_files(root, entries)

    def test_missing_duplicate_unsafe_or_noncanonical_mode_entry_rejected(self):
        for fault in ('missing', 'duplicate', 'unsafe', 'mode'):
            entries = copy.deepcopy(self.entries)
            if fault == 'missing': entries.pop()
            if fault == 'duplicate': entries[1] = entries[0]
            if fault == 'unsafe': entries[0]['path'] = '/etc/../secret'
            if fault == 'mode': entries[0]['mode'] = 0o777
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                audit.verify_fixture_files(self.root, entries)

    def test_mounted_volume_requires_exact_device_name_filesystem_and_ro_flag(self):
        info = dict(FilesystemType='hfs', VolumeName=audit.VOLUME, MountPoint=str(self.root), DeviceNode='/dev/disk123')
        with patch.object(audit.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            audit.verify_volume(info, self.root, '/dev/disk123')
            for key in info:
                changed = {**info, key: 'wrong'}
                with self.subTest(key=key), self.assertRaises(ValueError):
                    audit.verify_volume(changed, self.root, '/dev/disk123')
        with patch.object(audit.os, 'statvfs', return_value=SimpleNamespace(f_flag=0)), self.assertRaises(ValueError):
            audit.verify_volume(info, self.root, '/dev/disk123')


class PersistencePlanTests(unittest.TestCase):
    def test_real_complete_raw_hash_header_and_fixture_reference_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); image = root / 'capture.raw'; reference = root / 'reference.json'
            with image.open('xb') as stream:
                stream.truncate(audit.IMAGE_BYTES)
                stream.seek(1024); stream.write(header())
                stream.seek(audit.IMAGE_BYTES - 1024); stream.write(header(101))
            reference.write_text(json.dumps({'files': []}))
            expected = audit.digest(image)
            with patch.object(audit, 'owned_path', side_effect=Path), patch.object(audit, 'validate_fixture') as fixture:
                result = audit.plan(image, expected, reference)
                self.assertEqual(result['image_sha256'], expected)
                self.assertEqual(result['fixture_reference_sha256'], audit.digest(reference))
                self.assertIs(result['durability_verified'], False)
                fixture.assert_called_once()
                for invalid in ('A' * 64, 'x', True, '0' * 64):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError): audit.plan(image, invalid, reference)
                alias = root / 'link.raw'; alias.symlink_to(image)
                with self.assertRaises(ValueError): audit.plan(alias, expected, reference)

    def test_default_plan_and_bad_inputs_never_run_external_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rejected in (False, True):
                output = root / ('bad' if rejected else 'plan')
                args = ['audit.py', '--image', 'image.raw', '--expected-sha256', '1' * 64,
                        '--fixture', 'fixture.json', '--output', str(output)]
                with patch.object(sys, 'argv', args), patch.object(audit, 'owned_path', side_effect=Path), \
                        patch.object(audit, 'plan', return_value={'durability_verified': False},
                                     side_effect=ValueError('bad input') if rejected else None), \
                        patch.object(audit.subprocess, 'run') as command, contextlib.redirect_stdout(io.StringIO()):
                    if rejected:
                        with self.assertRaises(ValueError): audit.main()
                    else: self.assertEqual(audit.main(), 0)
                command.assert_not_called(); self.assertEqual(output.exists(), not rejected)

    def test_device_external_path_symlink_and_existing_output_refused(self):
        for path in (Path('/dev/disk0'), Path('/tmp/outside.raw')):
            with self.subTest(path=path), self.assertRaises(ValueError): audit.owned_path(path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'build/rpi5').mkdir(parents=True)
            link = root / 'build/rpi5/link'; link.symlink_to(root / 'build/rpi5/missing')
            with patch.object(audit, 'ROOT', root), self.assertRaises(ValueError): audit.owned_path(link)
            with patch.object(sys, 'argv', ['audit.py', '--image', 'image', '--expected-sha256', '1' * 64,
                                          '--fixture', 'reference', '--output', str(root)]), \
                    patch.object(audit, 'owned_path', side_effect=Path), patch.object(audit, 'plan') as plan, \
                    self.assertRaises(ValueError): audit.main()
            plan.assert_not_called()


class PersistenceExecutionTests(unittest.TestCase):
    def run_model(self, fault=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); image = root / 'capture.raw'; image.write_bytes(b'modeled image bytes')
            reference = root / 'fixture.json'; reference.write_text('{}')
            expected = audit.digest(image)
            output = root / 'audit'; output.mkdir()
            fixture_root = root / 'source'; fixture_root.mkdir()
            entries = original_files(fixture_root)
            record = dict(image=str(image), image_sha256=expected, fixture=str(reference),
                          fixture_files=entries, write_files=hfs_write_results.expected_entries(), durability_verified=False)
            attached = fault == 'pre-existing'; mounted = False; calls = []; detach = []

            def info():
                if not attached: return {'images': []}
                entity = {'dev-entry': '/dev/disk123', 'content-hint': ''}
                if mounted: entity['mount-point'] = str(output / 'readonly-mount')
                row = {'image-path': str(image), 'writeable': fault == 'writable', 'blocksize': 512,
                       'blockcount': audit.IMAGE_BYTES // 512, 'image-encrypted': False, 'system-entities': [entity]}
                rows = [row, copy.deepcopy(row)] if fault == 'ambiguous' else [row]
                return {'images': rows}

            def command(argv, **kwargs):
                nonlocal attached, mounted
                calls.append(list(argv))
                code = 0; data = b''
                if argv[:2] == ('hdiutil', 'info'): data = plistlib.dumps(info())
                elif argv[:2] == ('hdiutil', 'attach'):
                    self.assertTrue({'-readonly', '-noautofsck', '-nobrowse', '-noautoopen', '-plist'} <= set(argv))
                    self.assertEqual(argv[2], str(image)); attached = True; mounted = '-mountpoint' in argv
                    if fault == 'attach-timeout': raise subprocess.TimeoutExpired(argv, 180)
                    if mounted:
                        mount = output / 'readonly-mount'; original_files(mount)
                        for name, length, seed in hfs_write_results.VECTORS:
                            (mount / name).write_bytes(hfs_write_results.payload(length, seed))
                        if fault == 'old-file':
                            (mount / 'etc/proof.txt').chmod(0o644)
                            (mount / 'etc/proof.txt').write_bytes(b'corrupt')
                            (mount / 'etc/proof.txt').chmod(0o444)
                        if fault == 'new-file': (mount / hfs_write_results.VECTORS[0][0]).write_bytes(b'corrupt')
                    data = plistlib.dumps({'system-entities': []})
                elif argv[:2] == ('hdiutil', 'detach'):
                    self.assertEqual(argv, ('hdiutil', 'detach', '/dev/disk123'))
                    detach.append(argv[-1]); attached = False; mounted = False
                elif argv[0] == '/sbin/fsck_hfs':
                    self.assertEqual(argv, ('/sbin/fsck_hfs', '-fn', '/dev/disk123'))
                    if fault == 'fsck': code = 8
                elif argv[:2] == ('diskutil', 'info'):
                    data = plistlib.dumps(dict(FilesystemType='hfs', VolumeName=audit.VOLUME,
                        MountPoint=str(output / 'readonly-mount'), DeviceNode='/dev/disk123'))
                    if fault == 'image-change': image.write_bytes(b'changed')
                else: self.fail('Unexpected command: ' + repr(argv))
                return subprocess.CompletedProcess(argv, code, data, b'')

            def replan(*args):
                if audit.digest(image) != expected: raise ValueError('image changed')
                return record

            original_digest = audit.digest; source_reads = 0
            def digest(path):
                nonlocal source_reads
                if Path(path).resolve() == Path(audit.__file__).resolve():
                    source_reads += 1
                    if fault == 'source-change' and source_reads > 1: return 'f' * 64
                return original_digest(path)
            with patch.object(audit.subprocess, 'run', side_effect=command), patch.object(audit, 'digest', side_effect=digest), \
                    patch.object(audit, 'plan', side_effect=replan), \
                    patch.object(audit.os, 'statvfs', return_value=SimpleNamespace(f_flag=0 if fault == 'rw-mount' else os.ST_RDONLY)):
                if fault:
                    with self.assertRaises((ValueError, RuntimeError, subprocess.TimeoutExpired)):
                        audit.execute(record, output)
                else: audit.execute(record, output)
            result = json.loads((output / 'result.json').read_text())
            for item in result['commands']:
                if item['status'] == 'complete':
                    self.assertRegex(item['stdout_sha256'], r'^[0-9a-f]{64}$')
                    self.assertRegex(item['stderr_sha256'], r'^[0-9a-f]{64}$')
            return result, calls, detach, attached

    def test_exact_success_two_readonly_attachments_no_physical_gate_claim(self):
        result, calls, detach, attached = self.run_model()
        self.assertEqual(result['status'], 'local_image_audit_passed')
        self.assertIs(result['durability_verified'], False)
        self.assertTrue(result['readonly_fsck_verified'] and result['readonly_remount_verified'] and result['image_unchanged'])
        self.assertEqual(len(result['fixture_files']), 5); self.assertEqual(len(result['write_files']), 5)
        self.assertEqual(result['detach_count'], 2); self.assertFalse(attached)
        self.assertEqual(len(result['source_inputs_sha256']), 4)
        self.assertEqual(len([c for c in calls if c[:2] == ['hdiutil', 'attach']]), 2)

    def test_faults_preserve_failed_result_never_repair_retry_or_force_detach(self):
        for fault in ('fsck', 'old-file', 'new-file', 'rw-mount', 'image-change', 'source-change', 'writable', 'attach-timeout'):
            with self.subTest(fault=fault):
                result, calls, detach, attached = self.run_model(fault)
                self.assertEqual(result['status'], 'failed'); self.assertIs(result['durability_verified'], False)
                self.assertFalse(attached)
                expected = {'fsck': 'Read-only audit command failed', 'old-file': 'Original fixture file',
                            'new-file': 'Unexpected persistence file', 'rw-mount': 'Expected exact attached HFS',
                            'image-change': 'Image or ownership changed', 'source-change': 'Image or ownership changed',
                            'writable': 'Fresh image attachment is not read-only',
                            'attach-timeout': 'timed out'}[fault]
                self.assertIn(expected, result['error'])
                self.assertNotIn('-force', [arg for call in calls for arg in call])
                self.assertNotIn('-y', [arg for call in calls for arg in call])
                self.assertLessEqual(len([c for c in calls if c[0] == '/sbin/fsck_hfs']), 1)

    def test_preexisting_or_ambiguous_attachment_never_detached(self):
        for fault in ('pre-existing', 'ambiguous'):
            with self.subTest(fault=fault):
                result, calls, detach, attached = self.run_model(fault)
                self.assertEqual(result['status'], 'failed'); self.assertEqual(detach, []); self.assertTrue(attached)
                if fault == 'pre-existing': self.assertFalse(any(c[:2] == ['hdiutil', 'attach'] for c in calls))


if __name__ == '__main__': unittest.main()
