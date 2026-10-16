# SPDX-License-Identifier: BSD-2-Clause
"""Actual adapter + FDT + transaction, native architecture/FIFO doubles."""
import copy
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from .test_display_mailbox_fdt import fixture,cells
from .test_pcie_fdt import _encode_fdt,_node
ROOT=Path(__file__).resolve().parents[3]
class DisplayQueryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.sources=('display_query_adapter.c','display_mailbox_transaction.c','display_mailbox_get.c','display_mailbox_fdt.c','fdt.c','fdt_reg.c','ranges.c')
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(Path(__file__).with_name('display_query_adapter_host.c')),*[str(ROOT/'loader/rpi5'/n) for n in cls.sources],'-o',str(cls.work/'native')]
        p=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if p.returncode:raise AssertionError(p.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def tree(self):
        t=fixture();t['children'].append(_node('memory@0',{'device_type':b'memory\0','reg':cells(0,0,1,0)}));return t
    def run_case(self,count=2,mode=0,bad=0,tree=None):
        p=self.work/'tree.dtb';p.write_bytes(_encode_fdt(tree or self.tree()))
        r=subprocess.run([self.work/'native',p,str(count),str(mode),str(bad)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return r.stdout
    def test_actual_get_zero_one_two_and_no_reuse(self):
        for n in range(3):self.assertIn('rc=0',self.run_case(n))
    def test_actual_timeout_unmatched_no_pop_bad_response_changed_fdt_and_machine(self):
        for mode in (1,2,3,4,10,11,12,13,14,15,20,21):self.run_case(mode=mode)
    def test_fresh_architecture_revocation_before_and_after_real_callbacks(self):
        n=int(re.search(r'registers=(\d+)',self.run_case())[1])
        for bad in range(1,n+1):self.run_case(bad=bad)
    def test_ram_fixed_and_initrd_exclusion(self):
        t=self.tree();t['children'][-1]['properties']['reg']=cells(0,0x10000000,0,0x30000000);self.run_case(mode=30,tree=t)
        t=self.tree();t['children'].append(_node('chosen',{'linux,initrd-start':cells(0x9001000),'linux,initrd-end':cells(0x9002000)}));self.run_case(mode=30,tree=t)
        t=self.tree();t['children'].append(_node('reserved-memory',{'#address-cells':cells(2),'#size-cells':cells(2),'ranges':b''},
            _node('protected',{'reg':cells(0,0x9001000,0,4096)})));self.run_case(mode=30,tree=t)
    def test_a76_actual_sources_and_strict_cache_leaf(self):
        for n in (*self.sources,'display_query_arch.S','probe_display_query_main.c'):
            r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding','-fno-builtin','-mgeneral-regs-only',
                '-DRPI5_DISPLAY_QUERY_TAG="0123456789abcdef0123456789abcdef"','-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5'/n),'-o',str(self.work/(n+'.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
        s=(ROOT/'loader/rpi5/display_query_arch.S').read_text();self.assertIn('mov x1,#64',s)
        self.assertIn('page_cache rpi5_display_query_clean,cvac',s);self.assertIn('page_cache rpi5_display_query_invalidate,ivac',s)
        self.assertNotIn('civac',s);self.assertNotIn('msr',s)
if __name__=='__main__':unittest.main()
