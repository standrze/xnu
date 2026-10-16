# SPDX-License-Identifier: BSD-2-Clause
"""Actual loader/native geometry plus early contract mutation rejection."""
import copy
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_root42_ready_package as builder
from tools.rpi5 import check_root42_ready_package as checker


class RootReadyPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ['RPI5_ROOT42_READY_PACKAGE']).resolve()
        cls.manifest = json.loads((cls.package / 'manifest.json').read_text())

    def test_full_actual_native_payload_root_and_fdt(self):
        report = checker.inspect(self.package)
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual((report['root_nodes'], report['root_files']), (42, 30))
        self.assertEqual(report['kernel_sha256'], builder.KERNEL_SHA)
        self.assertEqual(report['terminal_watchdog_seconds'], 180)
        self.assertEqual(report['hardware_watchdog_seconds'], 15)
        self.assertEqual(report['native_handoff']['live_overlap_rejections'], 3)
        for k, v in builder.root_ready_contract().items():
            self.assertEqual(report[k], v)
        self.assertFalse(report['pi_executed'])
        self.assertFalse(report['networking'])

    def test_mount_contract_is_exact_not_a_claimed_boolean(self):
        for key, value in (('root_ready_marker', self.manifest['geometry']['root_mount_marker']),
                           ('root_ready_max_reports', 4), ('root_ready_max_reports', True),
                           ('root_ready_requires_mounted_readonly', False),
                           ('root_ready_requires_successful_reload', False)):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.manifest)
                changed[key] = value
                with self.assertRaisesRegex(ValueError, 'readiness contract'):
                    checker.inspect_record(self.package, changed)

    def test_same_root_and_one_actual_new_loader_tag(self):
        self.assertEqual(self.manifest['root_sha256'], builder.preceding.root_check.IMAGE_SHA)
        before, after = builder.derive_main(self.manifest['tag'])
        added = '    if (!text("' + builder.marker(self.manifest['tag']) + '\\r\\n")) return;\n'
        self.assertEqual(after.replace(added, ''), before)
        self.assertEqual(after.count(added), 1)
        self.assertIn('return start_secondaries(cpus);', after)
        self.assertEqual(after, (self.package / 'probe_main.c').read_text())
        for name, digest in builder.preceding.FROZEN.items():
            self.assertEqual(self.manifest['inputs_sha256'][str(builder.ROOT / 'tools/rpi5' / name)], digest)


if __name__ == '__main__':
    unittest.main()
