# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only actual stack receipts and negative admission of drift/dynamics."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import audit_gem_batch_stack as a
from tools.rpi5 import audit_gem_rp1_loader_stack as l
ROOT=a.ROOT
PACKAGE=ROOT/'build/rpi5/gem-dma-batch-trial-20261014-v4'
MEASURE=ROOT/'build/rpi5/gem-batch-stack-measurements-20261014-v6/measurements.json'
EARLY=ROOT/'build/rpi5/gem-batch-startup-stack-20261014-v1/audit.json'
LOADER=ROOT/'build/rpi5/gem-rp1-loader-stack-20261014-v1/measurements.json'
class BatchStackEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(a.sha(PACKAGE/'manifest.json'),'d1a36b98b4d050a085d5f03d66b113bfb6c4fac74fbd750411827c3264591a16')
        self.block=patch('subprocess.run',side_effect=AssertionError('Byte-only replay'))
        self.block.start();self.addCleanup(self.block.stop)
    def test_actual_owned_components_not_generic_os_bound(self):
        r=a.owned_bounds(PACKAGE,MEASURE,EARLY)
        self.assertEqual(r['maximum_owned_path_bytes'],11728)
        self.assertEqual(r['core_frame_bytes'],3408)
        self.assertLess(r['maximum_owned_path_bytes']+512,16384)
        self.assertFalse(r['whole_kernel_stack_proven'])
        self.assertFalse(r['panic_irq_scheduler_stack_proven'])
        self.assertTrue(any('arbitration' in s for s in r['standard_kernel_assumptions']))
    def test_exact_source_drift_and_dynamic_frame_rejected(self):
        original=a.sha;source=next(iter(json.loads(MEASURE.read_bytes())['inputs_sha256']))
        with patch.object(a,'sha',side_effect=lambda p:'0'*64 if str(p)==source else original(p)):
            with self.assertRaises(ValueError):a.owned_bounds(PACKAGE,MEASURE,EARLY)
        actual=a.frames
        def dynamic(path):
            result=actual(path)
            if Path(path).name=='kernel-rpi5_gem_ring_batch.su':
                result['rpi5_gem_ring_batch']['kind']='dynamic'
            return result
        with patch.object(a,'frames',side_effect=dynamic):
            with self.assertRaises(ValueError):a.owned_bounds(PACKAGE,MEASURE,EARLY)
    def test_actual_separate_rp1_loader_phase_and_original32k_stack(self):
        r=l.inspect(PACKAGE,LOADER)
        self.assertEqual(r['maximum_conservative_bytes'],21088)
        self.assertEqual(r['stack_bytes'],32768)
        self.assertEqual(r['minimum_remaining_bytes'],11680)
        self.assertFalse(r['record_finalization_nested'])
        self.assertFalse(r['display_allocator_nested'])
    def test_loader_drift_and_invalid_elf_fail(self):
        original=l.sha;source=next(iter(json.loads(LOADER.read_bytes())['inputs_sha256']))
        with patch.object(l,'sha',side_effect=lambda p:'0'*64 if str(p)==source else original(p)):
            with self.assertRaises(ValueError):l.inspect(PACKAGE,LOADER)
        with patch.object(Path,'read_bytes',return_value=b'not an ELF'):
            with self.assertRaises(ValueError):l.elf_code('/tmp/inert-not-real')
if __name__=='__main__':unittest.main()
