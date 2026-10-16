# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import tempfile
import unittest
from tools.rpi5 import build_pcie_gem_identify_kernel as b


class GEMKernelTests(unittest.TestCase):
    def test_exact_parent_and_three_object_composition(self):
        parent,_,pins=b.inputs();before,after,changed=b.objects(Path('/tmp/gem-only-offline-fixture'))
        self.assertEqual(b.audit.sha(b.BASE/'manifest.json'),b.BASE_SHA)
        self.assertEqual({p.name for p in changed},{'BCM2712PCIePHYTransport.cpp.o','rp1_decode_cycle.c.o'})
        self.assertEqual(after[-1].name,'rp1_gem_identify.c.o');self.assertEqual(len(after),len(before)+1)
        for name in ('rpi5_pcie_fw_owner.inc','rpi5_pcie_irq_owner.inc','rpi5_pcie_watchdog_owner.inc'):
            with tempfile.TemporaryDirectory(prefix='gem-frozen-owner-') as directory:
                folder=Path(directory)/'overlay';sources=b.profile.emit(folder)
                self.assertEqual((folder/name).read_bytes(),(b.profile.FROZEN/name).read_bytes())
                self.assertEqual(len(sources),3)
        self.assertFalse(b.contract()['endpoint_register_writes']);self.assertEqual(b.contract()['endpoint_read_bound'],32)

    def test_checked_linked_kernel_if_present(self):
        directory=b.ROOT/'build/rpi5/pcie-gem-identify-kernel-20261013-v1'
        if not (directory/'manifest.json').exists():self.skipTest('Distinct full kernel not built yet')
        m=json.loads((directory/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['kernel_sha256'],b.audit.sha(directory/'kernel.rp1-config'))
        self.assertEqual(m['gem_contract'],b.contract());self.assertEqual(m['logging_calls'],35)
        self.assertEqual(len(m['gem_object_replacements']),2)
        self.assertEqual(m['gem_added_objects'],[str(directory/'rp1_gem_identify.c.o')])
        self.assertEqual(len(m['gem_record_formats']),35)
        self.assertFalse(m['physical_success_proven']);self.assertFalse(m['endpoint_register_writes'])
        for name in m['gem_required_implementations']:
            self.assertEqual(len(b.engine.base.full.symbols((directory/'kernel.symbols').read_text()).get(name,[])),1)


if __name__=='__main__':unittest.main()
