# SPDX-License-Identifier: BSD-2-Clause
"""Actual allocation adapter/core with explicit host CPU/MMIO/firmware doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from .test_display_mailbox_fdt import fixture,cells
from .test_pcie_fdt import _encode_fdt,_node
ROOT=Path(__file__).resolve().parents[3]
class DisplayAllocateZeroAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.sources=('display_allocate_zero_adapter.c','display_allocate_transaction.c','display_allocate_wire.c','display_mailbox_fdt.c','fdt.c','fdt_reg.c','ranges.c')
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(Path(__file__).with_name('display_allocate_zero_adapter_host.c')),*[str(ROOT/'loader/rpi5'/n) for n in cls.sources],'-o',str(cls.work/'native')]
        p=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if p.returncode:raise AssertionError(p.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def tree(self):
        t=fixture();t['children'].append(_node('memory@0',{'device_type':b'memory\0','reg':cells(0,0,0,0x3f400000,0,0x40000000,1,0)}));return t
    def run_case(self,count=1,mode=0,bad=0,tree=None):
        p=self.work/'tree.dtb';p.write_bytes(_encode_fdt(tree or self.tree()))
        r=subprocess.run([self.work/'native',p,str(count),str(mode),str(bad)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');return r.stdout
    def test_actual_four_transactions_and_no_reuse(self):self.assertIn('rc=0',self.run_case())
    def test_actual_timeout_unmatched_no_pop_bad_response_changed_fdt_machine_and_geometry(self):
        for mode in (1,2,3,4,10,11,12,13,14,15,20,21,40,41,42,43,44,45,46,47,48,49):self.run_case(mode=mode)
        for n in (0,2):self.run_case(count=n)
    def test_every_fresh_architecture_checkpoint_fault_atomic_output(self):
        n=int(re.search(r'registers=(\d+)',self.run_case())[1])
        for bad in range(1,n+1):self.run_case(bad=bad)
    def test_allocation_excludes_fresh_ram_fixed_and_initrd(self):
        t=self.tree();t['children'][-1]['properties']['reg']=cells(0,0,1,0);self.run_case(mode=30,tree=t)
        # Even a RAM extent only in the rounded reservation tail forbids it.
        t=self.tree();t['children'][-1]['properties']['reg']=cells(0,0,0,0x3f400000,0,0x3fbea000,0,4096,0,0x40000000,1,0);self.run_case(mode=30,tree=t)
        t=self.tree();t['children'].append(_node('chosen',{'linux,initrd-start':cells(0x3f401000),'linux,initrd-end':cells(0x3f402000)}));self.run_case(mode=30,tree=t)
        t=self.tree();t['children'].append(_node('reserved-memory',{'#address-cells':cells(2),'#size-cells':cells(2),'ranges':b''},
            _node('protected',{'reg':cells(0,0x3f401000,0,4096)})));self.run_case(mode=30,tree=t)
    def test_a76_actual_sources(self):
        for n in self.sources:
            r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding','-fno-builtin','-mgeneral-regs-only',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5'/n),'-o',str(self.work/(n+'.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
    def test_only_candidate_prefix_admission_differs_from_frozen_adapter(self):
        old=(ROOT/'loader/rpi5/display_allocate_adapter.c').read_text()
        new=(ROOT/'loader/rpi5/display_allocate_zero_adapter.c').read_text()
        strip=lambda text:re.sub(r'/\*.*?\*/','',text,flags=re.S).strip()
        expected=old.replace('if((bus&UINT64_C(0xc0000000))!=UINT64_C(0xc0000000))return -1;',
            'if((bus&UINT64_C(0xc0000000))!=0)return -1;')
        self.assertNotEqual(strip(old),strip(new));self.assertEqual(strip(expected),strip(new))
if __name__=='__main__':unittest.main()

