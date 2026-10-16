# SPDX-License-Identifier: BSD-2-Clause
"""Actual protocol under doubles and separately linked A76 package checks."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/rpi5'))
import build_recovery_probe as builder
import check_recovery_package as checker


class RecoveryProtocolTests(unittest.TestCase):
    def test_actual_provider_and_real_lease_under_sanitizers(self):
        with tempfile.TemporaryDirectory(prefix='rpi5-recovery-host-') as name:
            output = Path(name)/'protocol'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-I', str(ROOT/'loader/rpi5'), str(ROOT/'tools/rpi5/tests/recovery_probe_host.c'),
                str(ROOT/'loader/rpi5/pcie_watchdog_lease.c'), '-o', str(output)], check=True, timeout=60)
            result = subprocess.run([str(output)], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('checks passed', result.stdout)


class RecoveryPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.manifest = builder.build()
        cls.package = Path(cls.manifest['image']).parent

    def inspect_with(self, manifest):
        with patch.object(checker.json, 'loads', side_effect=lambda text: copy.deepcopy(manifest)):
            return checker.inspect(self.package)

    def test_fresh_actual_a76_link_and_fixed_leaves(self):
        result = checker.inspect(self.package)
        self.assertTrue(result['preflight_pass'])
        self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['installation_admitted'])
        self.assertFalse(result['hardware_recovery_proven'])

    def test_unexpected_profile_and_hardware_claims_rejected(self):
        for key, value in [('profile', 'pcie2-readonly-access-v1'),
            *[(key, True) for key in builder.FALSE_CLAIMS], ('watchdog_reload_once_seconds', 60)]:
            with self.subTest(key=key):
                manifest = copy.deepcopy(self.manifest); manifest[key] = value
                with self.assertRaises(ValueError): self.inspect_with(manifest)

    def test_tag_command_stack_and_missing_evidence_rejected(self):
        for mutation in ('tag', 'command', 'stack', 'hash', 'foreign', 'tool'):
            with self.subTest(mutation=mutation):
                manifest = copy.deepcopy(self.manifest)
                if mutation == 'tag': manifest['trial_tag'] = '0'*32
                if mutation == 'command': manifest['commands'][0].append('-DRPI5_ALLOW_PCIE=1')
                if mutation == 'stack': manifest['stack_budget']['conservative_bytes'] = 0
                if mutation == 'hash': manifest['sha256'].pop(next(iter(manifest['sha256'])))
                if mutation == 'foreign': manifest['sha256']['../../etc/passwd'] = '0'*64
                if mutation == 'tool': manifest['tool_identity']['clang']['sha256'] = '0'*64
                with self.assertRaises(ValueError): self.inspect_with(manifest)

    def test_fixed_leaf_byte_comparison_detects_each_corruption(self):
        binary = self.package/'probe.bin'
        raw = binary.read_bytes()
        symbols = builder.symbols_for(self.package/'probe.elf')
        for name, expected in checker.expected_leaves().items():
            with self.subTest(name=name):
                damaged = bytearray(raw)
                offset = int(symbols[name][1], 16)-builder.BASE
                damaged[offset] ^= 1
                self.assertNotEqual(checker.leaf_words(bytes(damaged), symbols, name, 4*len(expected)), expected)

    def test_invalid_package_or_tag_rejected(self):
        with self.assertRaises(ValueError): checker.inspect(ROOT/'build/rpi5/bl33-probe-vszhh6o4')
        for tag in ('', 'A'*32, '../escape', 'a'*33):
            with self.assertRaises(ValueError): builder.commands_for(self.package, tag)


if __name__ == '__main__':
    unittest.main()
