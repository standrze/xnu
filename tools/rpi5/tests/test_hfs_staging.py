# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic staging evidence and remote guards; no SSH or device access."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_hfs_fixture as stage
from tools.rpi5.tests import test_serial_hfs_read_trial as serial_tests
from tools.rpi5.tests.test_hfs_stage_core import mbr
from tools.rpi5.tests.test_hfs_reference import baseline


class HFSStagingTests(unittest.TestCase):
    def setUp(self):
        self.factory = serial_tests.SerialHFSReadTrialTests()
        self.factory.setUp()
        self.addCleanup(self.factory.doCleanups)

    def bundle(self):
        paths = self.factory.bundle()
        paths.pop('reference')
        preflight = json.loads(paths['preflight'].read_text())
        Path(preflight['image']).write_bytes(stage.reference.__doc__.encode() + serial_tests.runner.SD_LOADER)
        preflight.update(hfs_readonly_trial=False, image_sha256=stage.sha256(Path(preflight['image'])))
        paths['preflight'].write_text(json.dumps(preflight))
        state = json.loads(paths['sd_trial'].read_text())
        state['image_sha256'] = preflight['image_sha256']
        paths['sd_trial'].write_text(json.dumps(state))
        return paths

    def load(self, paths):
        # The raw-image and native Mac checks have separate real fixture tests.
        # This test isolates evidence guards with tiny synthetic manifests.
        with patch.object(stage.reference, 'validate_fixture'):
            return stage.load_plan(paths)

    def test_plan_binds_passed_sd_trial_and_exact_nonboot_write_extents(self):
        paths = self.bundle()
        plan, _, hashes = self.load(paths)
        self.assertEqual(plan['evidence_sha256'], hashes)
        self.assertEqual(plan['write_extents'], [dict(region='data', start_byte=537919488, bytes=134217728),
                                                dict(region='mbr', start_byte=0, bytes=512)])
        self.assertTrue(plan['no_hfs_mount'] and plan['no_boot_image_change'] and plan['no_reboot'])

    def test_failed_incomplete_changed_or_wrong_image_sd_evidence_is_rejected(self):
        for field, value in (('status', 'failed'), ('reads', []), ('image_sha256', 'f' * 64)):
            paths = self.bundle()
            self.factory.mutate(paths['sd_trial'], lambda state: state.update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(paths)
        paths = self.bundle()
        (paths['sd_trial'].parent / 'serial.bin').write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            self.load(paths)

    def test_actual_hfs_image_is_not_accepted_as_isolated_sd_proof(self):
        paths = self.bundle()
        preflight = json.loads(paths['preflight'].read_text())
        image = Path(preflight['image'])
        image.write_bytes(image.read_bytes() + stage.HFS_LOADER)
        preflight['image_sha256'] = stage.sha256(image)
        paths['preflight'].write_text(json.dumps(preflight))
        self.factory.mutate(paths['sd_trial'], lambda state: state.update(image_sha256=preflight['image_sha256']))
        with self.assertRaises(ValueError):
            self.load(paths)

    def test_report_with_rehashed_readiness_only_capture_cannot_authorize_staging(self):
        paths = self.bundle()
        self.factory.rewrite_raw(paths, lambda data: b'\n'.join(data.split(b'\n')[:4]) + b'\n')
        output = paths['fixture'].parent / 'no-raw-reads'
        with patch.object(stage.reference, 'validate_fixture'), \
                patch.object(sys, 'argv', self.argv(paths, output, execute=True)), \
                patch.object(Path, 'is_relative_to', return_value=True), \
                patch.object(stage.subprocess, 'run') as network, self.assertRaises(ValueError):
            stage.main()
        network.assert_not_called()
        self.assertFalse(output.exists())

    def argv(self, paths, output, execute=False):
        args = ['stage_hfs_fixture.py', '--output', str(output)]
        for key, flag in (('fixture', 'fixture'), ('baseline', 'sd-baseline-reference'),
                          ('sd_trial', 'sd-trial'), ('preflight', 'preflight')):
            args.extend(('--' + flag, str(paths[key])))
        return args + (['--execute'] if execute else [])

    def test_default_generates_only_local_plan_without_network(self):
        paths = self.bundle()
        output = paths['fixture'].parent / 'local-plan'
        with patch.object(stage, 'ROOT', output.parent), \
                patch.object(stage.reference, 'validate_fixture'), \
                patch.object(sys, 'argv', self.argv(paths, output)), \
                patch.object(Path, 'is_relative_to', return_value=True), \
                patch.object(stage.subprocess, 'run') as network, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(stage.main(), 0)
        network.assert_not_called()
        plan = json.loads((output / 'plan.json').read_text())
        self.assertNotIn('run', plan)
        self.assertEqual(set(path.name for path in output.iterdir()), {'plan.json'})

    def test_invalid_proof_never_creates_output_or_runs_network_even_execute(self):
        paths = self.bundle()
        self.factory.mutate(paths['sd_trial'], lambda state: state.update(status='failed'))
        output = paths['fixture'].parent / 'must-not-exist'
        with patch.object(stage.reference, 'validate_fixture'), \
                patch.object(sys, 'argv', self.argv(paths, output, execute=True)), \
                patch.object(Path, 'is_relative_to', return_value=True), \
                patch.object(stage.subprocess, 'run') as network, self.assertRaises(ValueError):
            stage.main()
        self.assertFalse(output.exists())
        network.assert_not_called()

    def test_remote_timeout_preserves_partial_diagnostics_without_retry(self):
        paths = self.bundle()
        self.factory.mutate(paths['fixture'], lambda fixture: fixture.update(image='/synthetic/fixture.cdr'))
        output = paths['fixture'].parent / 'unknown-outcome'
        run = '/home/sandrzej/xnu-gate4-hfs-stage-abcdefgh'
        results = [SimpleNamespace(stdout=json.dumps(dict(run=run))), SimpleNamespace(returncode=0),
                   stage.subprocess.TimeoutExpired('ssh', 300, output=b'partial staging log', stderr=b'partial error')]
        with patch.object(stage.reference, 'validate_fixture'), \
                patch.object(sys, 'argv', self.argv(paths, output, execute=True)), \
                patch.object(Path, 'is_relative_to', return_value=True), \
                patch.object(stage.subprocess, 'run', side_effect=results) as network, \
                self.assertRaises(stage.subprocess.TimeoutExpired):
            stage.main()
        self.assertEqual(network.call_count, 3)
        self.assertEqual(json.loads((output / 'plan.json').read_text())['run'], run)
        self.assertEqual((output / 'remote.stdout').read_bytes(), b'partial staging log')
        self.assertEqual((output / 'remote.stderr').read_bytes(), b'partial error')
        self.assertTrue((output / 'outcome-unknown.txt').is_file())
        self.assertFalse((output / 'result.json').exists())

    def result_bundle(self):
        original = mbr()
        plan = dict(identity=baseline()['identity'], image_sha256='a' * 64,
                    mbr_sha256=hashlib.sha256(original).hexdigest(), run='/home/sandrzej/xnu-gate4-hfs-stage-abcdefgh')
        updated = stage.core.plan_mbr(original, plan['mbr_sha256'], stage.core.CARD_BYTES)
        layout = copy.deepcopy(plan['identity']['layout'])
        layout['partitions'].append(dict(node='/dev/mmcblk0p2', start=1050624, size=262144, type='af'))
        report = dict(status='staged', run=plan['run'], before_identity=plan['identity'], after_layout=layout,
                      image_sha256=plan['image_sha256'], mbr_before_hex=original.hex(),
                      mbr_before_sha256=plan['mbr_sha256'], mbr_after_sha256=hashlib.sha256(updated).hexdigest(),
                      boot_partition_sha256='b' * 64, boot_partition_bytes=536870912,
                      data_start_sector=1050624, data_sectors=262144, data_bytes_written=134217728,
                      mbr_bytes_written=512, publication_after_two_complete_data_readbacks=True,
                      boot_image_changed=False, hfs_mounted=False, rebooted=False,
                      data_readbacks=[dict(pass_number=n, bytes=134217728, sha256='a' * 64) for n in (1, 2)])
        return report, plan

    def test_result_requires_exact_layout_ranges_readbacks_and_protected_hash(self):
        report, plan = self.result_bundle()
        stage.validate_result(report, plan)
        for key, value in (('mbr_after_sha256', 'f' * 64), ('after_layout', {}), ('mbr_bytes_written', 1),
                           ('boot_partition_sha256', 'wrong'), ('boot_image_changed', True),
                           ('hfs_mounted', True), ('rebooted', 0), ('data_readbacks', report['data_readbacks'][:1])):
            bad = copy.deepcopy(report); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                stage.validate_result(bad, plan)
        bad = copy.deepcopy(report)
        bad['data_readbacks'][0]['pass_number'] = True
        with self.assertRaises(ValueError):
            stage.validate_result(bad, plan)

    def test_remote_wrong_root_card_mounted_or_automounter_fail_before_open(self):
        _, plan = self.result_bundle()
        source = stage.remote_source(plan)
        compile(source, '<hfs-staging>', 'exec')
        for fault in ('root', 'card', 'mounted', 'automounter'):
            def command(args, **kwargs):
                if args[0] == 'findmnt':
                    return 'wrong' if fault == 'root' else plan['identity']['root']
                if args[0] == 'sfdisk':
                    return json.dumps(dict(partitiontable=plan['identity']['layout']))
                return '\n'.join(key + '=' + value for key, value in plan['identity']['partition'].items())

            def read_text(path):
                if path.name == 'size':
                    return str(stage.core.CARD_BYTES // 512)
                return 'changed' if fault == 'card' else plan['identity']['card'][path.name]

            def run(args, **kwargs):
                return SimpleNamespace(returncode=(0 if fault == 'automounter' else 3) if args[0] == 'systemctl'
                                       else (0 if fault == 'mounted' else 1), stdout='')

            with patch('os.geteuid', return_value=0), patch('subprocess.check_output', side_effect=command), \
                    patch('subprocess.run', side_effect=run), \
                    patch('pathlib.Path.read_text', autospec=True, side_effect=read_text), \
                    patch('pathlib.Path.is_dir', return_value=True), patch('pathlib.Path.iterdir', return_value=iter(())), \
                    patch('pathlib.Path.exists', return_value=False), patch('os.open') as opened, \
                    self.subTest(fault=fault), self.assertRaises(RuntimeError):
                exec(compile(source, '<hfs-staging>', 'exec'), {})
            opened.assert_not_called()

    def remote_workflow(self, fault=None):
        """Execute the exact remote wrapper; bounded copy primitives tested separately.

        Only copy/hash bodies are replaced to avoid building a 512-MiB virtual
        filesystem. Descriptor guards, backup files, sync ordering, publication,
        revalidation, JSON persistence and finally-close paths remain real code.
        """
        report, plan = self.result_bundle()
        source = stage.remote_source(plan)
        namespace = {}
        exec(compile(source[:-len(stage.REMOTE)], '<staging-core>', 'exec'), namespace)
        run = Path(plan['run'])
        self.events, self.descriptors, self.saved = [], {}, {}
        self.closed = []
        published = False
        identity_calls = 0

        def command(args, **kwargs):
            nonlocal identity_calls
            if args[0] == 'findmnt':
                identity_calls += 1
                return 'wrong' if fault == 'post-root' and published else plan['identity']['root']
            if args[0] == 'sfdisk':
                return json.dumps(dict(partitiontable=report['after_layout'] if published else plan['identity']['layout']))
            fields = dict(TYPE='hfsplus', LABEL='XNU_G4_READ', PARTUUID='5ae1f07e-02') if args[-1].endswith('p2') \
                else plan['identity']['partition']
            return '\n'.join(key + '=' + value for key, value in fields.items())

        def read_text(path):
            if path == Path('/sys/block/mmcblk0/size'):
                return str(stage.core.CARD_BYTES // 512)
            if path == Path('/sys/class/block/mmcblk0p2/start'):
                return '1050624'
            if path == Path('/sys/class/block/mmcblk0p2/size'):
                return '262144'
            return 'changed' if fault == 'identity' and identity_calls == 3 else plan['identity']['card'][path.name]

        def open_fd(path, flags, *args):
            path = Path(path)
            if str(path).startswith('/dev/'):
                self.assertEqual(str(path), '/dev/mmcblk0')
            else:
                self.assertTrue(path == run or path == run.parent or path.parent == run or
                                str(path) == '/home/sandrzej/xnu-shell-passed-backup-20261011.bin')
            fd = 100 + len(self.descriptors)
            self.descriptors[fd] = (path, flags)
            self.events.append(('open', fd, str(path), flags))
            self.assertTrue(flags & os.O_NOFOLLOW)
            if flags & os.O_CREAT:
                self.assertTrue(flags & os.O_EXCL)
                self.assertEqual(args, (0o600,))
            return fd

        def fstat(fd):
            path, _ = self.descriptors[fd]
            is_card = str(path) == '/dev/mmcblk0'
            return SimpleNamespace(st_mode=stat.S_IFBLK if is_card else stat.S_IFREG, st_nlink=1,
                                   st_size=stage.core.DATA_BYTES if path.name == 'fixture.cdr' else 16660000,
                                   st_rdev=180 if fault == 'descriptor' and is_card else 179)

        def ioctl(fd, request, *args):
            nonlocal published
            if request == 0x80081272:
                return struct.pack('=Q', stage.core.CARD_BYTES)
            self.assertEqual(request, 0x125f)
            self.events.append(('publish', fd))
            if fault == 'publication':
                raise OSError('partition reread failed')
            published = True
            return 0

        def write(fd, data, offset):
            path, _ = self.descriptors[fd]
            self.assertNotEqual(str(path), '/dev/mmcblk0')
            self.assertEqual(offset, 0)
            self.saved[path.name] = data
            self.events.append(('save', path.name))
            return len(data)

        def hash_span(fd, offset, size):
            path, _ = self.descriptors[fd]
            if path.name == 'fixture.cdr':
                return plan['image_sha256']
            return 'bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f'

        def backup(card, dest):
            self.events.append(('backup', card, dest))
            if fault == 'backup':
                raise RuntimeError('backup readback differs')
            return report['boot_partition_sha256']

        def stage_data(card, image, original, old_hash, image_hash, boot_hash):
            self.assertEqual(self.descriptors[card][1] & os.O_ACCMODE, os.O_RDWR)
            self.assertEqual(self.descriptors[image][1] & os.O_ACCMODE, os.O_RDONLY)
            self.assertEqual(original, mbr())
            self.assertEqual((old_hash, image_hash, boot_hash),
                             (plan['mbr_sha256'], plan['image_sha256'], report['boot_partition_sha256']))
            for name in ('mbr.before.bin', 'mbr.planned.bin', 'plan.json'):
                self.assertIn(('save', name), self.events)
            for directory in (run, run.parent):
                self.assertTrue(any(event[0] == 'sync' and self.descriptors[event[1]][0] == directory
                                    for event in self.events))
            self.events.append(('stage', card))
            if fault == 'staging':
                raise RuntimeError('data readback differs')
            return copy.deepcopy(report)

        namespace.update(hash_span=hash_span, backup_boot=backup, stage_payload=stage_data)
        output = io.StringIO()
        with patch('os.geteuid', return_value=0), patch('subprocess.check_output', side_effect=command), \
                patch('subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')) as processes, \
                patch('pathlib.Path.read_text', autospec=True, side_effect=read_text), \
                patch('pathlib.Path.resolve', autospec=True, side_effect=lambda path: path), \
                patch('pathlib.Path.stat', return_value=SimpleNamespace(st_dev=17)), \
                patch('pathlib.Path.is_dir', return_value=True), \
                patch('pathlib.Path.iterdir', autospec=True, side_effect=lambda path: iter((run / 'fixture.cdr',)) if path == run else iter(())), \
                patch('pathlib.Path.exists', return_value=False), \
                patch('os.statvfs', return_value=SimpleNamespace(f_bavail=0 if fault == 'space' else 1024, f_frsize=1024*1024)), \
                patch('os.open', side_effect=open_fd), patch('os.fstat', side_effect=fstat), \
                patch('os.stat', return_value=SimpleNamespace(st_rdev=179)), \
                patch('os.pread', return_value=mbr()), patch('os.pwrite', side_effect=write), \
                patch('os.fsync', side_effect=lambda fd: self.events.append(('sync', fd))), \
                patch('os.close', side_effect=self.closed.append), patch('fcntl.ioctl', side_effect=ioctl), \
                patch('fcntl.flock'), contextlib.redirect_stdout(output):
            # systemctl returns inactive, whereas findmnt returns unmounted.
            processes.side_effect = lambda args, **kwargs: SimpleNamespace(
                returncode=3 if args[0] == 'systemctl' else 1, stdout='')
            exec(compile(stage.REMOTE, '<staging-wrapper>', 'exec'), namespace)
        return json.loads(output.getvalue()), plan

    def test_remote_full_workflow_preserves_backups_before_write_and_balances_descriptors(self):
        report, plan = self.remote_workflow()
        stage.validate_result(report, plan)
        self.assertEqual(sorted(self.closed), sorted(self.descriptors))
        self.assertEqual(json.loads(self.saved['plan.json']), plan)
        self.assertEqual(json.loads(self.saved['result.json']), report)
        self.assertLess(next(n for n, event in enumerate(self.events) if event[0] == 'stage'),
                        next(n for n, event in enumerate(self.events) if event[0] == 'publish'))
        self.assertEqual(sum(event[0] == 'stage' for event in self.events), 1)

    def test_remote_late_failure_closes_all_fds_never_retries_or_claims_success(self):
        for fault in ('space', 'descriptor', 'backup', 'identity', 'staging', 'publication', 'post-root'):
            with self.subTest(fault=fault), self.assertRaises((RuntimeError, OSError)):
                self.remote_workflow(fault)
            self.assertEqual(sorted(self.closed), sorted(self.descriptors))
            self.assertNotIn('result.json', self.saved)
            self.assertLessEqual(sum(event[0] == 'stage' for event in self.events), 1)
            if fault in ('space', 'descriptor', 'backup', 'identity', 'staging'):
                self.assertFalse(any(event[0] == 'publish' for event in self.events))


if __name__ == '__main__':
    unittest.main()
