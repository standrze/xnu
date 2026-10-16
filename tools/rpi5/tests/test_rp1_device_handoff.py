# SPDX-License-Identifier: BSD-2-Clause
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree,_encode_fdt,_cells
ROOT=Path(__file__).resolve().parents[3]


class RP1DeviceHandoffTests(unittest.TestCase):
    def test_exact_six_pages_and_actual_kernel_decoder(self):
        tree=_synthetic_tree();bad=copy.deepcopy(tree)
        bad['children'][1]['children'][0]['properties']['num-lanes']=_cells(1)
        with tempfile.TemporaryDirectory(prefix='rp1-device-handoff-') as directory:
            work=Path(directory);exe=work/'host'
            names=('rp1_device_handoff','pcie_device_handoff','pcie_fdt','fdt','fdt_reg','memory_type','board_tree','cpu_tree','serial_tree','apple_dt')
            compiled=subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(ROOT/'loader/rpi5'),str(Path(__file__).with_name('rp1_device_handoff_host.c')),
                *[str(ROOT/'loader/rpi5'/(n+'.c')) for n in names],'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            for index,(data,mode) in enumerate(((_encode_fdt(tree),'accept'),(_encode_fdt(bad),'reject'),(b'not fdt','reject'))):
                fixture=work/(str(index)+'.dtb');fixture.write_bytes(data)
                result=subprocess.run([exe,fixture,mode],capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('RP1_DEVICE_PASS EXACT_NEW_PAGES=6' if mode=='accept' else 'RP1_DEVICE_REJECT',result.stdout)


if __name__=='__main__':unittest.main()
