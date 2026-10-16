# SPDX-License-Identifier: BSD-2-Clause
"""Actual combined loader audits; no hardware or target-runtime success claim."""
import copy
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_root42_pthread_package as builder
from tools.rpi5 import check_root42_pthread_package as checker


class PthreadPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ['RPI5_ROOT42_PTHREAD_PACKAGE']).resolve()

    def test_full_actual_source_link_payload_and_native_handoff(self):
        report = checker.inspect(self.package)
        self.assertTrue(report['preflight_pass'])
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual((report['root_nodes'], report['root_files']), (42, 30))
        self.assertEqual(report['kernel_sha256'], builder.KERNEL_SHA)
        self.assertEqual(report['terminal_watchdog_seconds'], 180)
        self.assertEqual(report['hardware_watchdog_seconds'], 15)
        self.assertTrue(report['native_handoff']['actual_kernel_map_decoder'])
        self.assertEqual(report['native_handoff']['live_overlap_rejections'], 3)
        self.assertFalse(report['pi_executed'])
        self.assertFalse(report['ssh_daemon'])
        self.assertFalse(report['networking'])

    def test_missing_closure_wrong_root_marker_and_deadline_rejected(self):
        original = json.loads((self.package / 'manifest.json').read_text())
        cases = [('generated_sha256', {}), ('headers_sha256', {}), ('commands', []),
            ('geometry', {}), ('terminal_watchdog_seconds', 3600),
            ('trial_marker', 'RPI5XNU:BL33:ROOT96_BATCH_TRIAL'),
            ('root_sha256', '0' * 64), ('embedded_init', {}), ('native_handoff', {})]
        for field, value in cases:
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                with self.assertRaises(ValueError):
                    checker.inspect_record(self.package, changed)

    def test_exact_one_tag_preserves_startup_and_frozen_derivation(self):
        manifest = json.loads((self.package / 'manifest.json').read_text())
        before, after = builder.derive_main(manifest['tag'])
        added = '    if (!text("' + builder.marker(manifest['tag']) + '\\r\\n")) return;\n'
        self.assertEqual(after.replace(added, ''), before)
        self.assertEqual(after.count(added), 1)
        self.assertIn('return start_secondaries(cpus);', after)
        self.assertIn('rpi5_psci_cpu_on(', after)
        self.assertEqual(after, (self.package / 'probe_main.c').read_text())
        for name, digest in builder.FROZEN.items():
            self.assertEqual(manifest['inputs_sha256'][str(builder.ROOT / 'tools/rpi5' / name)], digest)
        with self.assertRaisesRegex(ValueError, 'adaptation boundary'):
            builder.derived_source('build_root96_batch_package.py', [('not-an-anchor', '', 1)])


if __name__ == '__main__':
    unittest.main()
