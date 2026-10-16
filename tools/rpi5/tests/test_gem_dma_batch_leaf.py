# SPDX-License-Identifier: BSD-2-Clause
import struct
import unittest
from pathlib import Path
from tools.rpi5 import gem_dma_batch_leaf as leaf
ROOT=Path(__file__).resolve().parents[3]
OBJECT=ROOT/'build/rpi5/gem-dma-batch-objects-20261014-v1/provider.o'
class BatchLeafTests(unittest.TestCase):
    def test_actual_nullable_new_control_flow_and_original_negative(self):
        fixed=(OBJECT.parent.parent/'gem-dma-batch-objects-20261014-v2/transport.o').read_bytes()
        old=(OBJECT.parent/'transport.o').read_bytes()
        r=leaf.allocation_guard(fixed)
        self.assertTrue(r['null_before_constructor'] and r['phase3_on_failure'])
        with self.assertRaises(ValueError):leaf.allocation_guard(old)
        for value in (0xd503201f,0xb5000280,0xb4000281):
            raw=bytearray(fixed);struct.pack_into('<I',raw,r['null_branch'],value)
            with self.assertRaises(ValueError):leaf.allocation_guard(raw)
    def test_actual_a76_object_exact_bounded_cpu_access(self):
        r=leaf.inspect(OBJECT.read_bytes())
        self.assertEqual(set(r),{'write','read'})
        for row in r.values():
            self.assertEqual((row['loads'],row['stores'],row['instruction_bytes']),(16,16,128))
            self.assertTrue(row['no_calls_or_branches_inside'])
    def test_actual_instruction_branch_call_extent_pointer_and_order_mutations(self):
        original=OBJECT.read_bytes();report=leaf.inspect(original)
        for row in report.values():
            at=row['file_offset']
            for i in range(32):
                for value in (0x94000000,0xd63f0200,0xd503201f,0x14000000):
                    raw=bytearray(original);struct.pack_into('<I',raw,at+4*i,value)
                    with self.assertRaises(ValueError):leaf.inspect(raw)
            for bits in (1<<5,1<<10,1<<30):
                raw=bytearray(original);word=struct.unpack_from('<I',raw,at)[0]
                struct.pack_into('<I',raw,at,word^bits)
                with self.assertRaises(ValueError):leaf.inspect(raw)
            raw=bytearray(original);raw[at:at+8],raw[at+8:at+16]=raw[at+8:at+16],raw[at:at+8]
            with self.assertRaises(ValueError):leaf.inspect(raw)
        for cut in (0,31,len(original)-1):
            with self.assertRaises((ValueError,struct.error)):leaf.inspect(original[:cut])
