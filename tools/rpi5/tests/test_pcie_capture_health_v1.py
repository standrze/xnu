# SPDX-License-Identifier: BSD-2-Clause
import hashlib
from pathlib import Path
import unittest
from tools.rpi5 import pcie_capture_health_v1 as health

ROOT = Path(__file__).resolve().parents[3]


class CaptureHealthTests(unittest.TestCase):
    def test_actual_route_capture_does_not_hide_post_end_assertion(self):
        raw = (ROOT / 'build/rpi5/root-route-serial-20261013/serial.bin').read_bytes()
        report = health.inspect(raw, 'cd2027571ae6b55d64b77772a6ec0d5c6af4248d5ba2d3b0807093dbc192f1b9')
        self.assertEqual(report['bytes'], 30080)
        self.assertEqual(report['complete_terminal_lines'], 1)
        self.assertTrue(report['post_terminal_fault_observed'])
        self.assertEqual({r['signature'] for r in report['faults']}, {'panic(cpu ', 'Assertion failed:'})
        self.assertFalse(report['clean_trial_acceptance_established'])

    def test_no_fault_signature_is_not_acceptance_or_id_success(self):
        raw = b'RPI5XNU:PCIEID:END OK=0\r\n'
        report = health.inspect(raw, hashlib.sha256(raw).hexdigest())
        self.assertFalse(report['runtime_fault_signature_observed'])
        self.assertFalse(report['clean_trial_acceptance_established'])
        self.assertNotIn('rp1_id_trial_pass', report)

    def test_prior_config_capture_also_has_the_unreported_post_end_panic(self):
        raw = (ROOT / 'build/rpi5/rp1-config-v3-serial-20261013/serial.bin').read_bytes()
        report = health.inspect(raw, '9e89d72db9a4d7d77707ad16ad03f6fc84d8a1f42e9032d814f4bcab839738f7')
        self.assertTrue(report['post_terminal_fault_observed'])
        self.assertTrue(report['runtime_fault_signature_observed'])
        self.assertFalse(report['clean_trial_acceptance_established'])

    def test_entire_trace_scanned_and_missing_or_duplicate_end_not_inferred(self):
        end = b'RPI5XNU:PCIEID:END OK=1\r\n'
        for raw, count, after in ((b'panic(cpu 0)\n' + end, 1, False),
                (end + b'\0panic(cpu 0)\n', 1, True),
                (end + end + b'Assertion failed:\n', 2, False),
                (b'FAILED_STOP', 0, False)):
            with self.subTest(raw=raw):
                report = health.inspect(raw, hashlib.sha256(raw).hexdigest())
                self.assertTrue(report['runtime_fault_signature_observed'])
                self.assertEqual(report['complete_terminal_lines'], count)
                self.assertEqual(report['post_terminal_fault_observed'], after)

    def test_digest_empty_size_and_type_fail_closed(self):
        for raw, digest in ((b'changed', '0' * 64), (b'', hashlib.sha256(b'').hexdigest()),
                (b'x' * (health.MAX_BYTES + 1), '0' * 64), ('text', '0' * 64), (b'a', 'bad')):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                health.inspect(raw, digest)


if __name__ == '__main__':
    unittest.main()
