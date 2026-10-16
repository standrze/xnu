# SPDX-License-Identifier: BSD-2-Clause
import json
import tempfile
import unittest
from pathlib import Path
from tools.rpi5 import build_pcie_root_forward_kernel as b


class RootForwardKernelTests(unittest.TestCase):
    def test_private_source_preserves_owners_and_existing_cores(self):
        with tempfile.TemporaryDirectory(prefix='root-forward-overlay-') as directory:
            folder=Path(directory)/'overlay';sources=b.profile.emit(folder)
            self.assertEqual([p.name for p in sources],['BCM2712PCIePHYTransport.cpp','pcie_root_forward.c'])
            for name in ('BCM2712PCIeFWTransport.inc','rpi5_pcie_fw_owner.inc','rpi5_pcie_irq_owner.inc',
                'rpi5_pcie_watchdog_owner.inc','rp1_gem_identify.c','rp1_decode_cycle.c','rp1_bars_assign.c',
                'BCM2712PCIeControllerPolicy.h','BCM2712RP1DecodeTransport.inc'):
                self.assertEqual((folder/name).read_bytes(),(b.profile.FROZEN/name).read_bytes())
            self.assertIn('rootForward.state!=RPI5_ROOT_FORWARD_LIVE',(folder/'BCM2712RP1GEMIdentifyTransport.inc').read_text())
            self.assertEqual(b.contract()['native_modeled_pm_checks'],63372)
            self.assertEqual(len(b.references()),5)

    def test_actual_linked_one_replacement_one_new_object(self):
        folder=b.ROOT/'build/rpi5/pcie-root-forward-kernel-20261013-v1'
        if not (folder/'manifest.json').exists():self.skipTest('Kernel not built yet')
        m=json.loads((folder/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['profile'],b.PROFILE);self.assertEqual(m['root_forward_contract'],b.contract())
        self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(len(m['root_forward_object_replacements']),1);self.assertEqual(len(m['root_forward_added_objects']),1)
        self.assertNotIn('gem_object_replacements',m);self.assertTrue(m['gem_and_decode_core_objects_unchanged'])
        self.assertEqual(m['logging_calls'],42);self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        self.assertEqual(m['primary_source_references'],b.references())
        for reference in b.references():self.assertEqual(m['inputs_sha256'][reference['path']],reference['sha256'])


if __name__=='__main__':unittest.main()
