# SPDX-License-Identifier: BSD-2-Clause
import unittest
from tools.rpi5 import gem_mapping_predicate_profile as p

class MappingPredicateDiagnosticTests(unittest.TestCase):
    def test_exact_observed_parent_failure_is_pinned(self):
        import json
        evidence=json.loads(p.EVIDENCE.read_bytes())
        self.assertFalse(evidence['capture_valid']);self.assertTrue(evidence['zero_serial_tx'])
        self.assertTrue(evidence['independent_normal_nvme_linux_return_verified'])
        self.assertEqual(evidence['capture_error'],'Incomplete/error/non-zero-TX capture')
        serial=(p.EVIDENCE.parent/'serial.bin').read_bytes()
        self.assertIn(b'RPI5XNU:PCIEID:DMA_PREP STEP=14 ERROR=-13 BYTES=32768 PACKETS=0',serial)
    def test_only_passive_mapping_diagnostics_are_added(self):
        before=p.parent.derive();after=p.derive()
        self.assertEqual(set(before),set(after))
        changed={name for name in before if before[name]!=after[name]}
        self.assertEqual(changed,{'BCM2712GEMDMABatch.h','BCM2712GEMDMABatch.cpp',
            'BCM2712PCIePHYTransport.h','BCM2712PCIeIDTrialProgress.inc'})
        c=after['BCM2712GEMDMABatch.cpp'].decode()
        self.assertEqual(c.count('return fail('),31)
        self.assertIn('mappingReason_=41;return true;',c)
        self.assertEqual(c.count('translated_nc('),3)
        self.assertEqual(c.count('pmap_cache_attributes('),2)
        for forbidden in ('setBusMaster','enableIRQ','queueHead','queueTail'):
            self.assertNotIn(forbidden,c)
    def test_predicate_ids_are_unique_and_cover_both_pages(self):
        c=p.derive()['BCM2712GEMDMABatch.cpp'].decode()
        import re
        ids=[int(x) for x in re.findall(r'return fail\((\d+),',c)]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn('offset<AllocationBytes;offset+=Alignment',c)
        self.assertIn('return fail(31,page,attr&VM_WIMG_MASK,0,pa,0,0)',c)
        self.assertIn('return fail(33,page,attr&VM_WIMG_MASK,1,pa,translation.read_par,translation.write_par)',c)
        self.assertIn('return fail(36,page,attr&VM_WIMG_MASK,2,pa,translation.read_par,translation.write_par)',c)
    def test_at_sequence_and_reporting_boundary_are_preserved(self):
        files=p.derive();c=files['BCM2712GEMDMABatch.cpp'].decode();progress=files['BCM2712PCIeIDTrialProgress.inc'].decode()
        sequence='mrs %0, par_el1\\n\\tat s1e1r, %3\\n\\tisb\\n\\tmrs %1, par_el1\\n\\t"\n        "at s1e1w, %3\\n\\tisb\\n\\tmrs %2, par_el1\\n\\tmsr par_el1, %0\\n\\tisb'
        self.assertIn(sequence,c)
        body=c[c.index('bool BCM2712GEMDMABatch::mapping() const'):c.index('\n}\n\n/* SPDX-License-Identifier: BSD-2-Clause */\nbool BCM2712GEMDMABatch::route')]
        for forbidden in ('kprintf','IOLog','bcopy','memcpy','flush','invalidate','clean_dcache'):
            self.assertNotIn(forbidden,body)
        self.assertEqual(progress.count('RPI5XNU:PCIEID:DMA_MAP REASON='),1)
if __name__=='__main__':unittest.main()
