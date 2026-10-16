# SPDX-License-Identifier: BSD-2-Clause
"""Host model, actual cross-link and immutable-root checks; not Pi execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5.prepare_statprobe_root import prepare
from tools.rpi5.prepare_zsh_trial_root import files_from
from tools.rpi5.ramroot import build
from tools.rpi5.tests.test_prepare_pid1 import fixture
from tools.rpi5 import check_statprobe_package as package_check

ROOT = Path(__file__).resolve().parents[3]


class StatprobeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.program = Path(cls.temporary.name) / 'statprobe-model'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DRPI5_STATPROBE_HOST_TEST',
                        str(ROOT / 'tools/rpi5/user/statprobe.c'),
                        str(ROOT / 'tools/rpi5/tests/statprobe_model.c'),
                        '-o', str(cls.program)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def model(self, fault, status=0):
        result = subprocess.run([str(self.program), fault], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, status, result.stderr)
        return result.stdout

    def test_reads_both_open_profiles_and_reports_actual_raw_buffers(self):
        value = self.model('none')
        self.assertEqual(value.count('STATPROBE:PATH='), 4)
        self.assertEqual(value.count('STATPROBE:F_DUPFD_10=10\n'), 4)
        self.assertEqual(value.count('STATPROBE:OPEN_FLAGS=131072\n'), 2)
        self.assertIn('STATPROBE:STAT64=-2\nSTATPROBE:RAW=' + 'a5' * 144, value)
        self.assertIn('STATPROBE:DUP_DATA=000102030405060708090a0b0c0d0e0f\n', value)
        self.assertIn('STATPROBE:ORIGINAL_DATA=101112131415161718191a1b1c1d1e1f\n', value)
        self.assertIn('STATPROBE:END:DIAGNOSTIC_ONLY\n', value)

    def test_wrong_mode_is_recorded_not_replaced_with_regular_file_success(self):
        value = self.model('wrong-mode')
        self.assertIn('STATPROBE:MODE=292\nSTATPROBE:ISREG=0\nSTATPROBE:ISDIR=0\n', value)
        self.assertNotIn('STATPROBE:ISREG=1\n', value)

    def test_errno_results_remain_distinguishable(self):
        for fault, line in (('stat-error', 'STAT64=-5'), ('dup-error', 'F_DUPFD_10=-22'),
                            ('open-error', 'OPEN=-6'), ('read-error', 'DUP_READ=-5')):
            with self.subTest(fault=fault):
                value = self.model(fault)
                self.assertIn('STATPROBE:' + line + '\n', value)
                self.assertIn('STATPROBE:BUFFER_DAMAGE=0\n', value)

    def test_guards_and_invalid_duplicate_stop_before_further_syscalls(self):
        for fault in ('overrun', 'fstat-overrun', 'dup-alias'):
            with self.subTest(fault=fault):
                value = self.model(fault, 1)
                self.assertIn('STATPROBE:BUFFER_DAMAGE=1\n', value)
                self.assertNotIn('STATPROBE:DUP_READ=', value)
        self.assertEqual(self.model('usage', 2), '')

    def test_root_preserves_every_file_mode_and_rejects_collisions_and_bad_hashes(self):
        exe = bytes(fixture())
        files = {name: (exe, 0o555) for name in ('/sbin/launchd', '/bin/sh', '/bin/zsh')}
        files['/etc/zsh-smoke.zsh'] = (b'keep me\n', 0o444)
        baseline = build(files)[0]
        pin = hashlib.sha256(baseline).hexdigest()
        image, report = prepare(baseline, exe, pin)
        self.assertEqual({k: v for k, v in files_from(image).items() if k != '/bin/statprobe'}, files)
        self.assertFalse(report['pi_executed'])
        self.assertFalse(report['script_file_acceptance'])
        with self.assertRaises(ValueError): prepare(baseline, exe, '0' * 64)
        with self.assertRaises(ValueError): prepare(baseline, b'not Mach-O', pin)
        for name in ('/bin/statprobe', '/etc/statprobe-missing'):
            collision = build({**files, name: (b'data', 0o444)})[0]
            with self.subTest(path=name), self.assertRaises(ValueError):
                prepare(collision, exe, hashlib.sha256(collision).hexdigest())

    def test_real_static_arm64_link_preserves_physical_root_and_refuses_output_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'diagnostic'
            command = [sys.executable, str(ROOT / 'tools/rpi5/prepare_statprobe_root.py'),
                       '--output-dir', str(out)]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            manifest = json.loads((out / 'manifest.json').read_text())
            image = (out / 'ramdisk.bin').read_bytes()
            actual = files_from(image)
            original = files_from(Path(manifest['input_root']).read_bytes())
            self.assertEqual({k: v for k, v in actual.items() if k != '/bin/statprobe'}, original)
            self.assertEqual(manifest['output_nodes'], 25)
            self.assertEqual(hashlib.sha256(image).hexdigest(), manifest['output_sha256'])
            symbols = subprocess.check_output(['xcrun', 'nm', '-u', str(out / 'statprobe')], text=True)
            self.assertEqual(symbols.strip(), '')
            again = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((out / 'ramdisk.bin').read_bytes(), image)

    def test_prepared_package_has_no_hardware_acceptance_and_wrong_pins_fail(self):
        package = ROOT / 'build/rpi5/bl33-probe-cijenc9s'
        if not package.exists():
            self.skipTest('Separate diagnostic boot package is not prepared')
        report = package_check.inspect(package)
        self.assertTrue(report['preflight_pass'])
        for field in ('pi_executed', 'script_file_acceptance', 'abi_root_cause_proven',
                      'networking', 'durability', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(report[field], field)
        for pin in ('INIT_SHA', 'PROBE_SHA', 'KERNEL_SHA'):
            with self.subTest(pin=pin), patch.object(package_check, pin, '0' * 64):
                with self.assertRaises(ValueError): package_check.inspect(package)


if __name__ == '__main__':
    unittest.main()
