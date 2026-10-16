# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_root96_batch_package as builder
from tools.rpi5 import check_root96_batch_package as checker


class BatchPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_ROOT96_BATCH_PACKAGE']).resolve()

    def test_full_source_link_native_root_and_retained_handoff(self):
        report=checker.inspect(self.package)
        self.assertTrue(report['preflight_pass']);self.assertTrue(all(report['checks'].values()))
        self.assertEqual(report['root_nodes'],41);self.assertEqual(report['root_files'],29)
        self.assertTrue(report['native_handoff']['actual_kernel_map_decoder'])
        self.assertEqual(report['native_handoff']['live_overlap_rejections'],3)
        self.assertFalse(report['pi_executed'])

    def test_missing_maps_tag_and_geometry_are_rejected(self):
        original=json.loads((self.package/'manifest.json').read_text())
        cases=[('generated_sha256',{}),('headers_sha256',{}),('commands',[]),('geometry',{}),
               ('watchdog_ready_profile','root96-terminal-ready-kernel-v1'),('terminal_watchdog_seconds',3600),
               ('trial_marker','unrelated'),('root_sha256','0'*64),('embedded_init',{}),('native_handoff',{})]
        for field,value in cases:
            with self.subTest(field=field):
                changed=copy.deepcopy(original);changed[field]=value
                with self.assertRaises(ValueError):checker.inspect_record(self.package,changed)

    def test_main_change_is_exactly_one_tag_preserving_all_startup_code(self):
        m=json.loads((self.package/'manifest.json').read_text());before,after=builder.derive_main(m['tag'])
        added='    if (!text("'+builder.marker(m['tag'])+'\\r\\n")) return;\n'
        self.assertEqual(after.replace(added,''),before)
        self.assertEqual(after.count(added),1)
        self.assertIn('return start_secondaries(cpus);',after)
        self.assertIn('rpi5_psci_cpu_on(',after)
        self.assertEqual(after,(self.package/'probe_main.c').read_text())


if __name__=='__main__':unittest.main()
