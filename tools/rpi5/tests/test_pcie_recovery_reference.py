# SPDX-License-Identifier: BSD-2-Clause
"""Boot-reference parsing, exact RO mount ownership and no-network default."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import capture_pcie_recovery_reference as capture
from tools.rpi5 import pcie_recovery_reference_core as core

BOOT = '8512e93e-ec70-4715-bb02-d118afe393ed'
CONFIG = b'[all]\narm_64bit=1\narmstub=bl31.bin\nkernel=probe.bin\nset_reboot_order=0xf6\nkernel_watchdog_timeout=15\n'
EEPROM = '[all]\nBOOT_UART=1\nPOWER_OFF_ON_HALT=0\nBOOT_ORDER=0xf461\n'


class RecoveryReferenceTests(unittest.TestCase):
    def fixture(self, directory):
        files = {'config.txt': CONFIG, 'probe.bin': b'known-image', 'bl31.bin': b'trusted-firmware'}
        for name, data in files.items(): (directory / name).write_bytes(data)
        identity = dict(identity={'card': {'cid': 'exact'}}, boot_id=BOOT, hostname='kamidana')
        plan = dict(identity_binding=dict(expected=identity['identity'], linux_boot_id_after_write=BOOT),
                    protected_files_sha256={n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
                    protected_extents_sha256={'mbr': '1'*64, 'boot': '2'*64})
        snapshots, commands = [], []
        def snapshot(*args):
            snapshots.append(args)
            name = next(n for n, extent in core.EXTENTS.items() if extent == args)
            return dict(device=args[0], bytes=args[2], sha256=plan['protected_extents_sha256'][name])
        original = types.SimpleNamespace(identity=lambda binding: copy.deepcopy(identity),
                                         command=lambda *args: EEPROM, snapshot=snapshot)
        state = dict(mounted=False, id=55, replace=False, lookup=0, fail_unmount=False)
        def run(args):
            commands.append(args)
            if args[0] == 'findmnt':
                if not state['mounted']: return subprocess.CompletedProcess(args, 1, '', '')
                state['lookup'] += 1
                row = dict(id=state['id']+(state['replace'] and state['lookup'] > 1),
                           source=core.BOOT_NODE, fstype='vfat', target=str(directory),
                           options='ro,nosuid,nodev,noexec,relatime')
                return subprocess.CompletedProcess(args, 0, json.dumps({'filesystems': [row]}), '')
            if args[0] == 'mount':
                self.assertEqual(args, ['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', core.BOOT_NODE, str(directory)])
                state['mounted'] = True
            elif args[0] == 'umount':
                self.assertEqual(args, ['umount', str(directory)])
                if state['fail_unmount']: return subprocess.CompletedProcess(args, 1, '', 'busy')
                state['mounted'] = False
            else: raise AssertionError('Unexpected command: ' + repr(args))
            return subprocess.CompletedProcess(args, 0, '', '')
        return plan, original, run, state, snapshots, commands

    def context(self, directory):
        # The real guard requires an empty mountpoint before mounting. These
        # fixture files stand in for its filesystem only after the fake mount.
        real_iterdir = Path.iterdir
        def entries(path):
            if path == directory: return iter(())
            return real_iterdir(path)
        return patch.multiple(core, MOUNTPOINT=str(directory)), patch.object(core.os, 'geteuid', return_value=0), \
            patch.object(core, 'boot_properties', return_value={'boot-mode': 6, 'partition': 1, 'tryboot': 0}), \
            patch.object(Path, 'iterdir', entries)

    def test_config_subset_conditional_unknown_duplicate_and_watchdog_target(self):
        p = core.config_profile(CONFIG)
        self.assertTrue(p['configured_nvme_only_next_order']); self.assertEqual(p['kernel_watchdog_timeout'], 15)
        p = core.config_profile(b'[none]\nset_reboot_order=0xf1\n[pi5]\nset_reboot_order=0xf6\n')
        self.assertTrue(p['configured_nvme_only_next_order'])
        for change in (b'[tryboot]\n', b'include extra.txt\n', b'set_reboot_order=0xf1\n',
                       b'[gpio0=1]\n', b'kernel_watchdog_timeout=bad\n', b'kernel=' + b'x'*100+b'\n'):
            self.assertFalse(core.config_profile(CONFIG+change)['supported_subset'])
        with self.assertRaises(ValueError): core.config_profile(b'\0')
        files = dict(config_profile=p, alternate_files_present={n: False for n in core.ALTERNATE_FILES})
        files['config_profile'] = core.config_profile(CONFIG+b'kernel_watchdog_partition=2\n')
        self.assertFalse(core.configured_return(files))
        files['config_profile'] = core.config_profile(CONFIG.replace(b'timeout=15', b'timeout=60'))
        self.assertTrue(core.configured_return(files))
        self.assertEqual(files['config_profile']['kernel_watchdog_timeout'], 60)

    def test_eeprom_order_is_right_to_left_not_recovery_evidence(self):
        p = core.eeprom_profile(EEPROM)
        self.assertEqual(p['order_right_to_left'], [1, 6, 4, 15]); self.assertTrue(p['persistent_order_sd_first'])
        for value in ('[tryboot]\nBOOT_ORDER=0xf6', 'BOOT_ORDER=0xf461\nBOOT_ORDER=0xf6',
                      'BOOT_ORDER=0x100000000', 'BOOT_ORDER=0', 'BOOT_UART=1'):
            with self.assertRaises(ValueError): core.eeprom_profile(value)
        self.assertFalse(core.LIMITATIONS['watchdog_reset_return_proven'])

    def test_protected_regular_files_hashes_bounds_symlinks_and_alternates(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve(); plan, *_ = self.fixture(work)
            directory = core.os.open(work, core.os.O_RDONLY | core.os.O_DIRECTORY)
            try:
                r = core.read_files(directory, plan['protected_files_sha256'])
                self.assertTrue(core.configured_return(r))
                (work / 'autoboot.txt').symlink_to('/definitely/not/read')
                self.assertFalse(core.configured_return(core.read_files(directory, plan['protected_files_sha256'])))
                with self.assertRaises(ValueError): core.read_files(directory, {'../config.txt': '0'*64})
                (work / 'probe.bin').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'differs'): core.read_files(directory, plan['protected_files_sha256'])
                (work / 'probe.bin').unlink(); (work / 'probe.bin').symlink_to(work / 'bl31.bin')
                with self.assertRaises(OSError): core.read_files(directory, plan['protected_files_sha256'])
            finally: core.os.close(directory)

    def test_exact_readonly_mount_record_refuses_rw_alias_bad_id_and_ambiguity(self):
        row = dict(id=55, source=core.BOOT_NODE, fstype='vfat', options='ro,nosuid,nodev,noexec', target=core.MOUNTPOINT)
        def run(value): return lambda args: subprocess.CompletedProcess(args, 0, json.dumps({'filesystems': value}), '')
        self.assertEqual(core.mount_record(run([row]))['id'], 55)
        for field, value in (('source', '/dev/nvme0n1p1'), ('fstype', 'hfsplus'), ('id', True),
                             ('id', 0), ('options', 'rw,nosuid,nodev,noexec'), ('options', 0), ('target', '/')):
            changed = dict(row); changed[field] = value
            with self.assertRaises(ValueError): core.mount_record(run([changed]))
        for rows in ([], [row, row]):
            with self.assertRaises(ValueError): core.mount_record(run(rows))

    def test_actual_capture_ro_sequence_complete_hashes_and_independent_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve(); plan, original, run, state, reads, commands = self.fixture(work)
            with self.context(work)[0], self.context(work)[1], self.context(work)[2], self.context(work)[3]:
                r = core.capture_recovery(plan, original, run)
                core.validate_recovery(r, plan)
            self.assertTrue(r['configured_one_shot_nvme_return']); self.assertFalse(state['mounted'])
            self.assertEqual(r['requested_watchdog_seconds'], 15)
            self.assertEqual(reads, list(core.EXTENTS.values())*2)
            self.assertEqual([c[0] for c in commands].count('mount'), 1)
            self.assertEqual([c[0] for c in commands].count('umount'), 1)
            for key in core.LIMITATIONS: self.assertFalse(r['limitations'][key])
            bad = copy.deepcopy(r); bad['operations']['sd_write_operations'] = False
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)
            bad = copy.deepcopy(r); bad['limitations']['watchdog_reset_return_proven'] = True
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)
            bad = copy.deepcopy(r); bad['boot_files']['config_profile']['set_reboot_order'] = True
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)
            bad = copy.deepcopy(r); bad['protected_after']['boot']['sha256'] = '9'*64
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)
            bad = copy.deepcopy(r); bad['bootloader_properties']['rng-seed'] = 'not-allowed'
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)
            bad = copy.deepcopy(r); bad['requested_watchdog_seconds'] = 60
            with self.assertRaises(ValueError): core.validate_recovery(bad, plan)

    def test_before_mount_identity_or_complete_byte_drift_refuses_without_mount(self):
        for failure in ('identity', 'blocks'):
            with tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary).resolve(); plan, original, run, state, _, commands = self.fixture(work)
                if failure == 'identity': original.identity = lambda _: (_ for _ in ()).throw(ValueError('identity'))
                else: plan['protected_extents_sha256']['boot'] = 'bad'; original.snapshot = lambda *args: dict(sha256='0'*64)
                with self.context(work)[0], self.context(work)[1], self.context(work)[2], self.context(work)[3]:
                    with self.assertRaises(ValueError): core.capture_recovery(plan, original, run)
                self.assertFalse(state['mounted']); self.assertEqual(commands, [])

    def test_bad_boot_file_unmounts_only_owned_readonly_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve(); plan, original, run, state, _, commands = self.fixture(work)
            (work / 'probe.bin').write_bytes(b'changed')
            with self.context(work)[0], self.context(work)[1], self.context(work)[2], self.context(work)[3]:
                with self.assertRaisesRegex(ValueError, 'differs'): core.capture_recovery(plan, original, run)
            self.assertFalse(state['mounted']); self.assertEqual(commands[-1], ['umount', str(work)])

    def test_replaced_or_busy_mount_is_not_blindly_unmounted_or_retried(self):
        for failure in ('replace', 'fail_unmount'):
            with tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary).resolve(); plan, original, run, state, _, commands = self.fixture(work)
                state[failure] = True
                with self.context(work)[0], self.context(work)[1], self.context(work)[2], self.context(work)[3]:
                    with self.assertRaises(ValueError): core.capture_recovery(plan, original, run)
                self.assertTrue(state['mounted'])
                self.assertEqual([c[0] for c in commands].count('umount'), failure == 'fail_unmount')
                self.assertEqual([c[0] for c in commands].count('mount'), 1)

    def test_boot_properties_filter_precedes_read_and_big_endian_decode(self):
        names = []
        def opened(path, mode):
            names.append(str(path)); self.assertEqual(mode, 'rb')
            self.assertIn(path.name, core.BOOT_PROPERTIES)
            return io.BytesIO(b'\0\0\0\x06')
        with patch.object(Path, 'open', opened):
            self.assertEqual(core.boot_properties(), {name: 6 for name in core.BOOT_PROPERTIES})
        self.assertEqual(len(names), 3); self.assertFalse(any('seed' in n for n in names))
        with patch.object(Path, 'open', return_value=io.BytesIO(b'wrong')):
            with self.assertRaises(ValueError): core.boot_properties()

    def test_local_plan_default_no_ssh_overwrite_refusal_and_remote_compiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'plan'
            with patch('sys.argv', ['capture', '--linux-boot-id', BOOT, '--output-dir', str(out)]), \
                    patch.object(capture.subprocess, 'run') as command, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(capture.main(), 0); command.assert_not_called()
                with self.assertRaises(FileExistsError): capture.main()
            plan = json.loads((out / 'plan.json').read_text())
            self.assertFalse(plan['execute']); self.assertEqual(plan['operations'], core.OPERATIONS)
            snapshots = json.loads((out / 'source-snapshots.json').read_text())
            for name, row in snapshots.items():
                self.assertEqual(capture.sha(out / row['file']), plan['source_sha256'][name])
            compile(capture.remote_source(capture.load_plan(BOOT)), '<actual-remote-source>', 'exec')
            with patch.object(capture, 'HISTORY_SHA', {'plan.json': '0'*64}):
                with self.assertRaisesRegex(ValueError, 'history changed'): capture.load_plan(BOOT)
            with self.assertRaises(ValueError): capture.load_plan('not-a-uuid')

    def test_ssh_timeout_retains_partial_output_unknown_outcome_no_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'timeout'
            error = subprocess.TimeoutExpired(['ssh'], 180, output=b'partial', stderr=b'uncertain')
            with patch('sys.argv', ['capture', '--linux-boot-id', BOOT, '--output-dir', str(out), '--execute']), \
                    patch.object(capture.subprocess, 'run', side_effect=error) as command:
                with self.assertRaises(subprocess.TimeoutExpired): capture.main()
                self.assertEqual(command.call_count, 1)
            r = json.loads((out / 'result.json').read_text())
            self.assertFalse(r['passed']); self.assertEqual(r['remote_outcome'], 'unknown')
            self.assertEqual((out / 'partial.stdout').read_bytes(), b'partial')

    def test_source_drift_refuses_before_ssh(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'drift'
            good = capture.hashes()
            with patch('sys.argv', ['capture', '--linux-boot-id', BOOT, '--output-dir', str(out), '--execute']), \
                    patch.object(capture, 'hashes', side_effect=[good, {}]), \
                    patch.object(capture.subprocess, 'run') as command:
                with self.assertRaisesRegex(ValueError, 'Source changed'): capture.main()
                command.assert_not_called()
            self.assertFalse(json.loads((out / 'result.json').read_text())['ssh_attempted'])


if __name__ == '__main__': unittest.main()
