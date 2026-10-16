# SPDX-License-Identifier: BSD-2-Clause
"""Actual frozen allocator plus visible/retained consumer, explicit CPU/store doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_display_allocate_zero_adapter import DisplayAllocateZeroAdapterTests
from .test_pcie_fdt import _encode_fdt
ROOT=Path(__file__).resolve().parents[3]
class DisplayVisibleAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.sources=('display_allocate_zero_adapter.c','display_allocate_transaction.c','display_allocate_wire.c',
            'display_visible_adapter.c','display_visible_patch.c','display_allocation_retained.c','display_mailbox_fdt.c','fdt.c','fdt_reg.c','ranges.c')
        r=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'loader/rpi5'),str(ROOT/'tools/rpi5/tests/display_visible_adapter_host.c'),
            *[str(ROOT/'loader/rpi5'/n) for n in cls.sources],str(ROOT/'osfmk/console/iso_font.c'),'-o',str(cls.work/'native')],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_case(self,mode=0,bad=0,tree=None,count=1):
        path=self.work/'tree.dtb';path.write_bytes(_encode_fdt(tree or DisplayAllocateZeroAdapterTests().tree()))
        r=subprocess.run([self.work/'native',path,str(count),str(mode),str(bad)],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return r.stdout
    def test_same_boot_allocator_then_exact_store_phase_and_retained_range_exclusions(self):self.assertIn('stores=20480',self.run_case())
    def test_all_frozen_allocation_failure_classes_prevent_drawing(self):
        for mode in (1,2,3,4,10,11,12,13,14,15,20,21,40,41,42,43,44,45,46,47,48,49):self.run_case(mode)
        for count in (0,2):self.run_case(count=count)
    def test_fresh_architecture_fdt_absolute_deadline_and_mid_store_time_failures(self):
        for mode in (50,51,52,53):self.run_case(mode)
        for bad in (1,2,3,10,20,50,100,200,500,1000,10000,50000):self.run_case(bad=bad)
    def test_all_actual_sources_compile_for_a76_without_warnings(self):
        for name in self.sources:
            r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding',
                '-fno-builtin','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5'/name),'-o',str(self.work/(name+'.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
