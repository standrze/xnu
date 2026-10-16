# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_packet_leaves as builder


class PacketLeavesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = builder.ROOT / 'build/rpi5/apple-ssh-packet-leaves-we7s8n0w'
        cls.report = json.loads((cls.package / 'manifest.json').read_text())

    def test_all_recorded_inputs_and_generated_outputs(self):
        for field in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in self.report[field].items():
                self.assertEqual(builder.sha(Path(name)), digest, name)
        self.assertTrue(self.report['reused_memset_source_identical_to_current'])
        self.assertTrue(self.report['original_feature_config_unchanged'])

    def test_actual_original_apple_leaf_boundaries(self):
        result = subprocess.run([self.package / 'ssh-leaves-host'], capture_output=True,
            text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['leaf_stdout'])
        self.assertEqual(self.report['compare_cases'], 131842)

    def test_actual_packet_cipher_with_apple_leaf_implementations(self):
        result = subprocess.run([self.package / 'sshpacketprobe-apple-leaves-host'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['packet_stdout'])
        self.assertEqual(self.report['valid_packet_cases'], 48)
        self.assertEqual(self.report['rejected_packet_cases'], 5036)

    def test_only_six_real_evp_gaps_remain(self):
        self.assertFalse(self.report['target_link_complete'])
        self.assertEqual(self.report['target_missing_symbols'], builder.GAPS)
        self.assertNotIn('"_memset_s"', self.report['target_link_error'])
        self.assertNotIn('"_timingsafe_bcmp"', self.report['target_link_error'])
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.report['target_archive']], text=True)
        for name in ('_memset_s', '_timingsafe_bcmp'):
            self.assertRegex(symbols, r'(?m)^[0-9a-f]+ T ' + name + '$')
        for name in ('entropy_qualified', 'timing_measurement', 'ssh_transport', 'pi_executed', 'installed'):
            self.assertFalse(self.report[name])


if __name__ == '__main__':
    unittest.main()
