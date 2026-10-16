# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_root43_packet_package as builder
from tools.rpi5 import check_root43_packet_package as checker


class PacketPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_ROOT43_PACKET_PACKAGE']).resolve()
        cls.manifest=json.loads((cls.package/'manifest.json').read_text())

    def test_full_actual_payload_fdt_and_state_confirmed_kernel(self):
        report=checker.inspect(self.package)
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual((report['root_nodes'],report['root_files']),(43,31))
        self.assertEqual(report['kernel_sha256'],builder.ready.KERNEL_SHA)
        self.assertEqual(report['native_handoff']['live_overlap_rejections'],3)
        self.assertEqual((report['terminal_watchdog_seconds'],report['hardware_watchdog_seconds']),(180,15))
        for k,v in builder.root_ready_contract().items():self.assertEqual(report[k],v)
        self.assertFalse(report['pi_executed']);self.assertFalse(report['networking'])

    def test_root_readiness_contract_mutations_reject(self):
        for k,v in (('root_ready_marker',self.manifest['root_ready_marker'].replace('NODES=43','NODES=42')),
                    ('root_ready_max_reports',4),('root_ready_max_reports',True),
                    ('root_ready_requires_mounted_readonly',False),('root_ready_requires_successful_reload',False)):
            altered=copy.deepcopy(self.manifest);altered[k]=v
            with self.assertRaisesRegex(ValueError,'readiness contract'):checker.inspect_record(self.package,altered)

    def test_only_payload_and_unique_loader_tag_change(self):
        before,after=builder.derive_main(self.manifest['tag'])
        added='    if (!text("'+builder.marker(self.manifest['tag'])+'\\r\\n")) return;\n'
        self.assertEqual(after.replace(added,''),before);self.assertEqual(after.count(added),1)
        self.assertEqual(after,(self.package/'probe_main.c').read_text())
        self.assertIn('return start_secondaries(cpus);',after)
        self.assertEqual(self.manifest['root_sha256'],builder.root_check.IMAGE_SHA)
        for n,h in builder.FROZEN.items():self.assertEqual(self.manifest['inputs_sha256'][str(builder.ROOT/'tools/rpi5'/n)],h)


if __name__=='__main__':unittest.main()
