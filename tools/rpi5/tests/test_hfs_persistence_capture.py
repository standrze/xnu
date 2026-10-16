# SPDX-License-Identifier: BSD-2-Clause
"""Post-write capture controls and explicitly modeled read-only SD metadata."""
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_hfs_persistence as capture
import hfs_persistence_capture_core as core
from tools.rpi5.tests import test_hfs_write_acceptance as acceptance_tests


class CaptureCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.data = bytes(range(256)) * 2
        self.source = self.root / 'source'; self.source.write_bytes(self.data)
        self.directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.directory)

    @contextlib.contextmanager
    def block_model(self, capacity=512, regular=False):
        original_open, original_stat, original_fstat = os.open, os.stat, os.fstat
        descriptors = set()
        def open_model(path, flags, *args, **kwargs):
            if str(path).startswith('/dev/'):
                self.assertEqual(str(path), '/dev/mmcblk0p2')
                self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
                self.assertTrue(flags & os.O_NOFOLLOW)
                fd = original_open(self.source, flags, *args, **kwargs); descriptors.add(fd); return fd
            return original_open(path, flags, *args, **kwargs)
        def fstat_model(fd):
            if fd in descriptors: return SimpleNamespace(st_mode=stat.S_IFREG if regular else stat.S_IFBLK, st_rdev=179)
            return original_fstat(fd)
        def stat_model(path, *args, **kwargs):
            if str(path) == '/dev/mmcblk0p2': return SimpleNamespace(st_rdev=179)
            return original_stat(path, *args, **kwargs)
        with patch.object(core, 'IMAGE_BYTES', 512), patch.object(core, 'CHUNK', 128), \
                patch.object(core.os, 'open', side_effect=open_model), patch.object(core.os, 'fstat', side_effect=fstat_model), \
                patch.object(core.os, 'stat', side_effect=stat_model), \
                patch.object(core.fcntl, 'ioctl', return_value=struct.pack('=Q', capacity)), \
                patch.object(core.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())):
            yield

    def test_copy_all_bytes_fsync_and_rehash_without_sd_write_descriptor(self):
        with self.block_model(), patch.object(core.os, 'fsync', wraps=os.fsync) as sync:
            result = core.copy_hfs(self.directory)
        self.assertEqual((self.root / core.IMAGE_NAME).read_bytes(), self.data)
        self.assertEqual(result, dict(device='/dev/mmcblk0p2', bytes=512, sha256=hashlib.sha256(self.data).hexdigest(), saved_as=core.IMAGE_NAME))
        self.assertEqual(sync.call_count, 3)

    def test_partial_writes_are_bounded_and_still_fully_read_back(self):
        original = os.pwrite
        with self.block_model(), patch.object(core.os, 'pwrite', side_effect=lambda fd, data, offset: original(fd, data[:32], offset)):
            core.copy_hfs(self.directory)
        self.assertEqual((self.root / core.IMAGE_NAME).read_bytes(), self.data)

    def test_short_read_stall_overflow_fsync_readback_wrong_capacity_type_or_existing_target_fail(self):
        for fault in ('read', 'zero', 'overflow', 'stall', 'fsync', 'readback', 'capacity', 'regular', 'existing', 'link'):
            target = self.root / core.IMAGE_NAME
            if target.exists() or target.is_symlink(): target.unlink()
            if fault == 'existing': target.write_bytes(b'preserve')
            if fault == 'link': target.symlink_to(self.source)
            with self.subTest(fault=fault), self.block_model(capacity=511 if fault == 'capacity' else 512,
                                                           regular=fault == 'regular'), contextlib.ExitStack() as stack:
                if fault == 'read': stack.enter_context(patch.object(core.os, 'pread', return_value=b'x'))
                if fault == 'zero': stack.enter_context(patch.object(core.os, 'pwrite', return_value=0))
                if fault == 'overflow': stack.enter_context(patch.object(core.os, 'pwrite', return_value=129))
                if fault == 'stall': stack.enter_context(patch.object(core.os, 'pwrite', side_effect=InterruptedError))
                if fault == 'fsync': stack.enter_context(patch.object(core.os, 'fsync', side_effect=OSError('sync failed')))
                if fault == 'readback':
                    original = os.pread
                    stack.enter_context(patch.object(core.os, 'pread', side_effect=lambda fd, length, offset:
                        b'x' * length if offset == 0 and stat.S_ISREG(os.fstat(fd).st_mode) else original(fd, length, offset)))
                with self.assertRaises((OSError, RuntimeError, ValueError)): core.copy_hfs(self.directory)
            self.assertEqual(self.source.read_bytes(), self.data)
            if fault == 'existing': self.assertEqual(target.read_bytes(), b'preserve')

    def test_raw_snapshot_fixed_extent_no_destination_and_no_extra_targets(self):
        with self.block_model():
            result = core.snapshot('/dev/mmcblk0p2', 512, 512)
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertFalse((self.root / core.IMAGE_NAME).exists())
        for args in (('/dev/nvme0n1p2', 128177930240, 512), ('/dev/mmcblk0', 128177930240, 513)):
            with patch.object(core.os, 'open') as opened, self.assertRaises(ValueError): core.snapshot(*args)
            opened.assert_not_called()


def plan_and_report():
    sha = hashlib.sha256(b'captured').hexdigest()
    plan = dict(host=capture.linux.HOST, expected={'exact': 'identity'},
        linux_boot_id_before_write='54b2ad20-73c0-4dc2-a6b7-c96506b04a0a',
        linux_boot_id_after_write='54b2ad20-73c0-4dc2-a6b7-c96506b04a0b',
        mbr_sha256='a' * 64, boot_sha256='b' * 64, fixture_sha256='c' * 64, nvme_backups=[],
        run='/home/sandrzej/xnu-gate4-hfs-persistence-abcdefgh')
    first = dict(device='/dev/mmcblk0p2', bytes=core.IMAGE_BYTES, sha256=sha)
    report = dict(status='captured_not_durability', run=plan['run'],
        identity=dict(identity=plan['expected'], boot_id=plan['linux_boot_id_after_write'], hostname='kamidana'),
        nvme_backups_verified=[], sd_write_operations=0, sd_mount_operations=0,
        image=plan['run'] + '/' + core.IMAGE_NAME, image_sha256=sha, durability_verified=False,
        protected=dict(mbr=dict(device='/dev/mmcblk0', bytes=512, sha256='a' * 64),
                       boot=dict(device='/dev/mmcblk0p1', bytes=536870912, sha256='b' * 64)),
        hfs_reads=[first, dict(first, saved_as=core.IMAGE_NAME), first])
    return plan, report


class CaptureEvidenceTests(unittest.TestCase):
    def test_result_requires_exact_new_boot_full_unchanged_protection_and_three_changed_hfs_reads(self):
        plan, report = plan_and_report(); capture.validate_report(report, plan)
        for fault in ('boot', 'root', 'writes', 'mounts', 'bool', 'unchanged', 'reads', 'size', 'fat', 'mbr', 'saved', 'image'):
            changed = copy.deepcopy(report)
            if fault == 'boot': changed['identity']['boot_id'] = plan['linux_boot_id_before_write']
            if fault == 'root': changed['identity']['identity'] = {}
            if fault == 'writes': changed['sd_write_operations'] = 1
            if fault == 'mounts': changed['sd_mount_operations'] = 1
            if fault == 'bool': changed['sd_write_operations'] = False
            if fault == 'unchanged': changed['image_sha256'] = plan['fixture_sha256']
            if fault == 'reads': changed['hfs_reads'].pop()
            if fault == 'size': changed['hfs_reads'][1]['bytes'] -= 1
            if fault == 'fat': changed['protected']['boot']['sha256'] = '0' * 64
            if fault == 'mbr': changed['protected']['mbr']['sha256'] = '0' * 64
            if fault == 'saved': changed['hfs_reads'][1]['saved_as'] = 'wrong'
            if fault == 'image': changed['image'] = '/dev/mmcblk0p2'
            with self.subTest(fault=fault), self.assertRaises(ValueError): capture.validate_report(changed, plan)

    def test_full_actual_transcript_and_launch_time_historical_validation_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state, raw, plan, result, bound = acceptance_tests.bundle()
            state.update(started_utc='2026-10-12T04:00:00+00:00', ended_utc='2026-10-12T04:05:00+00:00',
                         recorder_source_sha256=capture.recorder.sha256(Path(capture.recorder.__file__)))
            plan.update(expected={'exact': 'identity'}, fixture_sha256='d' * 64)
            result['write_trial_backups'] = {'after': {'mbr': {'sha256': 'a' * 64}, 'boot': {'sha256': 'b' * 64}}}
            trial = root / 'state.json'; trial.write_text(json.dumps(state)); (root / 'serial.bin').write_bytes(raw)
            with patch.object(capture.installer, 'evidence_path', side_effect=Path), \
                    patch.object(capture.recorder, 'load_inputs', return_value=(plan, result, bound)) as loader, \
                    patch.object(capture, 'backup_rows', return_value=[]):
                loaded = capture.load_plan(root / 'inputs', root / 'installed', trial, now=datetime(2026, 10, 12, 5, tzinfo=timezone.utc))
                self.assertIs(loaded['durability_verified'], False)
                self.assertEqual(loader.call_args.kwargs['now'], datetime(2026, 10, 12, 4, tzinfo=timezone.utc))
                for fault in ('failed', 'future', 'source', 'raw'):
                    changed = copy.deepcopy(state)
                    if fault == 'failed': changed['status'] = 'failed'
                    if fault == 'future': changed['ended_utc'] = '2026-10-13T04:00:00+00:00'
                    if fault == 'source': changed['recorder_source_sha256'] = '0' * 64
                    if fault == 'raw': (root / 'serial.bin').write_bytes(raw + b'changed')
                    trial.write_text(json.dumps(changed))
                    with self.subTest(fault=fault), self.assertRaises(ValueError):
                        capture.load_plan(root / 'inputs', root / 'installed', trial, now=datetime(2026, 10, 12, 5, tzinfo=timezone.utc))

    def test_state_or_raw_changed_during_full_backup_validation_is_rejected(self):
        for fault in ('state', 'raw'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); state, raw, plan, result, bound = acceptance_tests.bundle()
                state.update(started_utc='2026-10-12T04:00:00+00:00', ended_utc='2026-10-12T04:05:00+00:00',
                    recorder_source_sha256=capture.recorder.sha256(Path(capture.recorder.__file__)))
                trial = root / 'state.json'; trial.write_text(json.dumps(state)); (root / 'serial.bin').write_bytes(raw)
                def backups(*args):
                    target = trial if fault == 'state' else root / 'serial.bin'
                    target.write_bytes(target.read_bytes() + b'changed'); return []
                with self.subTest(fault=fault), patch.object(capture.installer, 'evidence_path', side_effect=Path), \
                        patch.object(capture.recorder, 'load_inputs', return_value=(plan, result, bound)), \
                        patch.object(capture, 'backup_rows', side_effect=backups), self.assertRaisesRegex(ValueError, 'changed during'):
                    capture.load_plan(root / 'inputs', root / 'installed', trial, now=datetime(2026, 10, 12, 5, tzinfo=timezone.utc))

    def test_rendered_remote_program_only_captures_and_rejects_same_boot_or_wrong_run(self):
        plan, _ = plan_and_report(); source = capture.remote_source(plan); compile(source, '<remote>', 'exec')
        self.assertNotIn('systemctl reboot', source); self.assertNotIn('mount -', source)
        for key, value in (('run', '/dev/mmcblk0'), ('linux_boot_id_after_write', plan['linux_boot_id_before_write'])):
            with self.subTest(key=key), self.assertRaises(ValueError): capture.remote_source({**plan, key: value})


class CaptureCoreGuardsTests(unittest.TestCase):
    def test_fresh_card_root_boot_and_unmounted_unheld_no_automounter_identity(self):
        plan, _ = plan_and_report()
        expected = dict(root=capture.linux.ROOT, layout={'exact': 'layout'}, card={'cid': 'cid', 'csd': 'csd'},
                        boot_partition={'TYPE': 'vfat', 'LABEL': 'XNU_PROBE'},
                        hfs_partition={'TYPE': 'hfsplus', 'LABEL': 'XNU_G4_READ'},
                        bytes=128177930240, partition_start=1050624, partition_sectors=262144)
        plan['expected'] = expected
        for fault in (None, 'root', 'hostname', 'boot', 'card', 'layout', 'partition', 'mounted', 'query', 'holder', 'automounter'):
            values = {'/sys/block/mmcblk0/device/cid': 'wrong' if fault == 'card' else 'cid',
                      '/sys/block/mmcblk0/device/csd': 'csd', '/sys/block/mmcblk0/size': str(250347520),
                      '/sys/class/block/mmcblk0p2/start': '1050624', '/sys/class/block/mmcblk0p2/size': '262144',
                      '/proc/sys/kernel/random/boot_id': plan['linux_boot_id_before_write'] if fault == 'boot' else plan['linux_boot_id_after_write']}
            original_path = Path
            def path(value):
                value = str(value)
                if value in values: return SimpleNamespace(read_text=lambda: values[value])
                if value.endswith('/holders'):
                    return SimpleNamespace(is_dir=lambda: True, iterdir=lambda: iter([1] if fault == 'holder' else []))
                if value == '/sys/block/mmcblk0/device':
                    class Base:
                        def __truediv__(self, child): return path(value + '/' + child)
                    return Base()
                if value == '/sys/class/block':
                    class SystemPath:
                        def __init__(self, name): self.name = name
                        def __truediv__(self, child):
                            new = self.name + '/' + child
                            return path(new) if new.endswith('/holders') else SystemPath(new)
                    return SystemPath(value)
                return original_path(value)
            def command(*args):
                if args[0] == 'hostname': return 'other' if fault == 'hostname' else 'kamidana'
                if args[0] == 'findmnt': return 'other' if fault == 'root' else capture.linux.ROOT
                if args[0] == 'sfdisk': return json.dumps({'partitiontable': {} if fault == 'layout' else expected['layout']})
                if args[0] == 'blkid':
                    key = 'boot_partition' if args[-1].endswith('p1') else 'hfs_partition'
                    return '\n'.join(k + '=' + ('wrong' if fault == 'partition' else v) for k, v in expected[key].items())
                self.fail(repr(args))
            def run(args, **kwargs):
                code = (0 if fault == 'mounted' else 2 if fault == 'query' else 1) if args[0] == 'findmnt' else (0 if fault == 'automounter' else 3)
                return subprocess.CompletedProcess(args, code, '', '')
            with self.subTest(fault=fault), patch.object(core, 'Path', side_effect=path), \
                    patch.object(core, 'command', side_effect=command), patch.object(core.subprocess, 'run', side_effect=run):
                if fault:
                    with self.assertRaises(ValueError): core.identity(plan)
                else: self.assertEqual(core.identity(plan)['identity'], expected)

    def test_actual_regular_backup_hash_type_size_nofollow_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); file = root / 'backup'; file.write_bytes(b'bytes')
            self.assertEqual(core.full_hash(file, 5), hashlib.sha256(b'bytes').hexdigest())
            with self.assertRaises(ValueError): core.full_hash(file, 4)
            alias = root / 'alias'; alias.symlink_to(file)
            with self.assertRaises(OSError): core.full_hash(alias, 5)
            alias.unlink(); os.link(file, alias)
            with self.assertRaises(ValueError): core.full_hash(file, 5)

    def test_complete_ordered_capture_rechecks_identity_backups_and_protected_bytes(self):
        for fault in (None, 'fat', 'mbr', 'unchanged', 'unstable', 'identity', 'nonfresh'):
            with tempfile.TemporaryDirectory() as directory:
                run = Path(directory).resolve(); plan, report = plan_and_report(); plan['run'] = str(run)
                mbr, boot = report['protected']['mbr'], report['protected']['boot']
                hfs = report['hfs_reads'][0]
                if fault == 'nonfresh': (run / 'existing').write_bytes(b'preserve')
                sequence = [dict(mbr), dict(boot), dict(hfs), dict(hfs), dict(mbr), dict(boot)]
                if fault == 'fat': sequence[1]['sha256'] = '0' * 64
                if fault == 'mbr': sequence[0]['sha256'] = '0' * 64
                if fault == 'unchanged': sequence[2]['sha256'] = plan['fixture_sha256']
                if fault == 'unstable': sequence[3]['sha256'] = '0' * 64
                identities = [{'exact': 'before'}, {'exact': 'other' if fault == 'identity' else 'before'}]
                with self.subTest(fault=fault), patch.object(core.os, 'geteuid', return_value=0), \
                        patch.object(core, 'identity', side_effect=identities) as identity, \
                        patch.object(core, 'verify_backups') as backups, patch.object(core, 'snapshot', side_effect=sequence) as reads, \
                        patch.object(core, 'copy_hfs', return_value=report['hfs_reads'][1]) as copy_file, \
                        patch.object(core, 'full_hash', return_value=report['image_sha256']):
                    if fault:
                        with self.assertRaises(ValueError): core.run_capture(plan)
                    else:
                        result = core.run_capture(plan); self.assertEqual(result['status'], 'captured_not_durability')
                        self.assertEqual(identity.call_count, 2); self.assertEqual(backups.call_count, 2)
                        self.assertEqual([c.args[0] for c in reads.call_args_list],
                            ['/dev/mmcblk0', '/dev/mmcblk0p1', '/dev/mmcblk0p2', '/dev/mmcblk0p2', '/dev/mmcblk0', '/dev/mmcblk0p1'])
                    if fault in ('fat', 'mbr', 'unchanged', 'nonfresh'): copy_file.assert_not_called()


class CaptureControllerTests(unittest.TestCase):
    def run_main(self, fault=None, execute=True):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'capture'; plan, report = plan_and_report()
            base = {key: value for key, value in plan.items() if key not in ('run', 'linux_boot_id_after_write')}
            argv = ['capture.py', '--inputs', 'inputs', '--installed', 'installed', '--trial', 'trial', '--output', str(output)]
            if execute: argv += ['--execute']
            boot = plan['linux_boot_id_before_write'] if fault == 'same-boot' else plan['linux_boot_id_after_write']
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[-1] == capture.linux.COMMAND:
                    stdout = 'kamidana\n' + capture.linux.ROOT + '\n' + boot + '\n'
                elif args[-1] == 'python3 -': stdout = json.dumps({'run': plan['run']})
                elif args[-1] == 'sudo -n python3 -':
                    if fault == 'timeout': raise subprocess.TimeoutExpired(args, 300, output=b'partial', stderr=b'diagnostic')
                    stdout = json.dumps(report)
                elif args[0] == 'scp': (output / core.IMAGE_NAME).write_bytes(b'captured'); stdout = ''
                else: self.fail('Unexpected command ' + repr(args))
                return subprocess.CompletedProcess(args, 0, stdout, '')
            with patch.object(sys, 'argv', argv), patch.object(Path, 'is_relative_to', return_value=True), \
                    patch.object(capture, 'load_plan', side_effect=lambda *a, **k: copy.deepcopy(base)), \
                    patch.object(capture.subprocess, 'run', side_effect=command), \
                    patch('prepare_hfs_fixture.inspect_image', return_value={'modeled': True}), \
                    contextlib.redirect_stdout(io.StringIO()):
                if fault:
                    with self.assertRaises((ValueError, subprocess.TimeoutExpired)): capture.main()
                else: self.assertEqual(capture.main(), 0)
            files = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
            return calls, files

    def test_default_local_plan_never_networks(self):
        calls, files = self.run_main(execute=False)
        self.assertEqual(calls, []); self.assertEqual(set(files), {'plan.json'})

    def test_success_has_one_capture_one_download_then_fresh_same_linux_check(self):
        calls, files = self.run_main()
        self.assertEqual(len(calls), 5); self.assertIn('capture.json', files)
        report = json.loads(files['capture.json']); self.assertIs(report['durability_verified'], False)
        self.assertEqual(report['image_sha256'], hashlib.sha256(b'captured').hexdigest())

    def test_same_boot_or_timeout_never_retries_downloads_or_claims_success(self):
        for fault, count in (('same-boot', 1), ('timeout', 3)):
            calls, files = self.run_main(fault)
            self.assertEqual(len(calls), count); self.assertNotIn('capture.json', files)
            self.assertFalse(any(call[0] == 'scp' for call in calls))
            if fault == 'timeout':
                self.assertIn('outcome-unknown.txt', files); self.assertEqual(files['remote.stdout'], b'partial')


if __name__ == '__main__': unittest.main()
