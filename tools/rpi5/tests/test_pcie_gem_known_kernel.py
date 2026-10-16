# SPDX-License-Identifier: BSD-2-Clause
import json
import unittest
from tools.rpi5 import build_pcie_gem_known_kernel as b


class GEMKnownKernelTests(unittest.TestCase):
    def test_actual_source_contract_masks(self):
        text=b.profile.gem_core((b.ROOT/'loader/rpi5/rp1_gem_identify.c').read_text())
        self.assertIn('v[3]&~UINT32_C(0x8000003f)',text);self.assertIn('v[4]&~UINT32_C(0x3f)',text)
        self.assertEqual(b.contract()['endpoint_read_bound'],32)
        self.assertEqual(b.contract()['native_modeled_pm_checks'],62044)

    def test_linked_candidate_and_all_pins(self):
        directory=b.ROOT/'build/rpi5/pcie-gem-identify-kernel-20261013-v2'
        if not (directory/'manifest.json').exists():self.skipTest('Not built yet')
        m=json.loads((directory/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['gem_contract'],b.contract());self.assertEqual(m['profile'],b.PROFILE)
        self.assertEqual(m['kernel_sha256'],b.audit.sha(directory/'kernel.rp1-config'))
        self.assertEqual(len(m['gem_object_replacements']),2);self.assertEqual(len(m['gem_added_objects']),1)
        self.assertTrue(m['prototype_not_used_for_hardware']);self.assertEqual(m['logging_calls'],35)
        self.assertEqual((directory/'overlay/rp1_gem_identify.c').read_text(),
            b.profile.gem_core((b.ROOT/'loader/rpi5/rp1_gem_identify.c').read_text()))


if __name__=='__main__':unittest.main()
