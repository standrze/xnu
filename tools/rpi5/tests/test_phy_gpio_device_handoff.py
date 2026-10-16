# SPDX-License-Identifier: BSD-2-Clause
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import pcie_phy_gpio_handoff_contract as actual
from tools.rpi5.tests.test_rp1_phy_gpio_observe import fixture_tree
from tools.rpi5.tests.test_pcie_fdt import _encode_fdt,_cells
ROOT=actual.ROOT
class PHYGPIOHandoffTests(unittest.TestCase):
    def test_actual_emitted_tree_and_kernel_map_nine_pages(self):
        from tools.rpi5.build_pcie_id_trial_package import LOADER
        result=actual.audit(LOADER)
        self.assertTrue(result['native_pass']);self.assertEqual(result['exact_rp1_pages'],9)
        self.assertTrue(result['excluded_adjacent_pages']);self.assertFalse(result['physical_execution'])
    def test_atomic_bad_binding_overlap_and_capacity(self):
        source=(ROOT/'tools/rpi5/tests/rp1_device_handoff_host.c').read_text()
        source=source.replace('#include "pcie_device_handoff_host.c"','#include "'+str(ROOT/'tools/rpi5/tests/pcie_device_handoff_host.c')+'"')
        source=source.replace('#include "rp1_device_handoff.h"','#include "phy_gpio_device_handoff.h"')
        source=source.replace('rpi5_rp1_device_handoff','rpi5_phy_gpio_device_handoff')
        source=source.replace('host.device.count+2','host.device.count+5')
        source=source.replace('const struct rpi5_range extra[2]={{0x1f00018000,0x1f0002c000},{0x1f00100000,0x1f00104000}};',
            'const struct rpi5_range extra[5]={{0x1f00018000,0x1f0002c000},{0x1f000d4000,0x1f000d8000},{0x1f000e4000,0x1f000e8000},{0x1f000f4000,0x1f000f8000},{0x1f00100000,0x1f00104000}};')
        source=source.replace('i<2;i++','i<5;i++').replace('full.device.count=30','full.device.count=27').replace('full.device.count=31','full.device.count=28')
        source=source.replace('EXACT_NEW_PAGES=6','EXACT_NEW_PAGES=9')
        tree=fixture_tree();bad=copy.deepcopy(tree)
        def mutate(n):
            if n['name']=='gpio@d0000':n['properties']['reg']=_cells(0xc0,0x400d4000,0,0xc000)
            for c in n['children']:mutate(c)
        mutate(bad)
        with tempfile.TemporaryDirectory(prefix='gpio-handoff-negative-') as name:
            folder=Path(name);src=folder/'host.c';src.write_text(source);exe=folder/'host'
            names=('phy_gpio_device_handoff','rp1_device_handoff','pcie_device_handoff','pcie_fdt','fdt','fdt_reg','memory_type','board_tree','cpu_tree','serial_tree','apple_dt')
            r=subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),str(src),*[str(ROOT/'loader/rpi5'/(n+'.c')) for n in names],'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            for raw,mode in ((_encode_fdt(tree),'accept'),(_encode_fdt(bad),'reject'),(b'not fdt','reject')):
                data=folder/'fixture.dtb';data.write_bytes(raw);r=subprocess.run([exe,data,mode],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
