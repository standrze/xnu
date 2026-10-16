# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import tempfile
import unittest
from tools.rpi5 import build_pcie_gem_capabilities_kernel as b


class GEMCapabilitiesKernelTests(unittest.TestCase):
    def test_exact_delta_bounded_logging_and_unchanged_owners(self):
        with tempfile.TemporaryDirectory(prefix='gem-cap-kernel-') as directory:
            folder=Path(directory)/'overlay'
            sources=b.profile.emit(folder)
            self.assertEqual([p.name for p in sources],['BCM2712PCIePHYTransport.cpp','rp1_gem_identify.c','rp1_gem_capabilities.c'])
            allowed={'BCM2712PCIePHYTransport.h','BCM2712RP1GEMIdentifyTransport.inc',
                'BCM2712RP1ConfigTransport.inc','rp1_gem_identify.c','rp1_gem_identify.h','BCM2712PCIeIDTrialProgress.inc'}
            for path in b.profile.FROZEN.iterdir():
                if path.is_file() and path.name not in allowed:
                    self.assertEqual(path.read_bytes(),(folder/path.name).read_bytes(),path.name)
            formats=re.findall(r'kprintf\("([^"\n]+)"',(folder/'BCM2712PCIeIDTrialProgress.inc').read_text())
            self.assertEqual(len(formats),47)
            self.assertTrue(all(len(re.findall(r'%(?!%)',fmt))<=16 for fmt in formats))
            self.assertTrue(formats[-1].startswith('RPI5XNU:PCIEID:END '))
            original,current,changes=b.objects(Path(directory))
            self.assertEqual(len(changes),2);self.assertEqual(len(current),len(original)+1)
            self.assertEqual(b.contract()['total_endpoint_reads'],48)
            self.assertLess(b.contract()['native_modeled_pm_checks'],65536)
            self.assertFalse(b.contract()['endpoint_register_writes'])

    def test_actual_complete_link_and_three_new_compiles(self):
        folder=b.ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1'
        if not (folder/'manifest.json').exists():self.skipTest('Distinct kernel not yet built')
        m=json.loads((folder/'manifest.json').read_text())
        b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['profile'],b.PROFILE)
        self.assertEqual(m['capabilities_contract'],b.contract())
        self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(len(m['compiles']),3)
        self.assertEqual(len(m['capabilities_object_replacements']),2)
        self.assertEqual(len(m['capabilities_added_objects']),1)
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        self.assertTrue(m['transport_class_layout']['constructors_allocators_vtable_and_methods_recompiled'])
        self.assertTrue(m['owner_client_core_secure_objects_unchanged'])
        self.assertEqual(m['logging_calls'],47)
        self.assertFalse(m['physical_trial_admitted'])


if __name__=='__main__':unittest.main()
