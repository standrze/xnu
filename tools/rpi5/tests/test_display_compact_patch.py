# SPDX-License-Identifier: BSD-2-Clause
"""Actual store-only patch with guarded host RAM and explicit callback faults."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class DisplayCompactPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        sources=[ROOT/'tools/rpi5/tests/display_compact_patch_host.c',ROOT/'loader/rpi5/display_compact_patch.c',ROOT/'osfmk/console/iso_font.c']
        r=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'loader/rpi5'),*map(str,sources),'-o',str(cls.work/'native')],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_case(self,mode=0,fail=0):
        r=subprocess.run([self.work/'native',str(mode),str(fail)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return r.stdout
    def test_exact_patch_pixels_alpha_counts_canaries_and_no_reuse(self):self.assertIn('stores=768',self.run_case())
    def test_each_owner_checkpoint_and_barrier_failure_stops_without_retry(self):
        for n in range(1,18):self.run_case(1,n)
        for n in (1,2,4,7,8):self.run_case(6,n)
    def test_time_regression_expiry_failure_and_store_faults(self):
        for mode in (2,3,4):
            for n in (1,2,3,96,97,384,785):self.run_case(mode,n)
        for n in (1,2,96,97,384,768):self.run_case(5,n)
    def test_invalid_geometry_extent_and_nonzero_prefix_have_zero_stores(self):
        for mode in (7,8,9):self.assertIn('stores=0',self.run_case(mode))
    def test_changed_callbacks_candidate_and_dirty_report_fail_closed(self):
        for mode in (10,11):self.assertIn('stores=1',self.run_case(mode))
        self.assertIn('stores=0',self.run_case(12))
    def test_actual_a76_store_and_barrier_leaves_have_no_reads(self):
        output=self.work/'arch.o'
        r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-c',str(ROOT/'loader/rpi5/display_compact_arch.S'),'-o',str(output)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        text=subprocess.check_output(['xcrun','llvm-objdump','-d',str(output)],text=True)
        self.assertRegex(text,r'str\s+w1, \[x0\]');self.assertEqual(text.count('str\t'),1)
        self.assertNotRegex(text,r'\b(?:ldr|ldp|dc|msr|tlbi)\s')
if __name__=='__main__':unittest.main()

