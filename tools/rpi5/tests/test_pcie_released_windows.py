# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
class ReleasedWindowsTests(unittest.TestCase):
    def test_production_programmer_and_released_windows_checker(self):
        with tempfile.TemporaryDirectory() as temporary:
            program=Path(temporary)/'released'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                str(Path(__file__).with_name('pcie_released_windows_host.c')),
                str(ROOT/'loader/rpi5/pcie_windows.c'),str(ROOT/'loader/rpi5/pcie_released_windows.c'),
                '-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('READS=90 CALLBACKS=277 FAILURE_POSITIONS=277 DEPENDENCY_POSITIONS=277',result.stdout)
    def test_a76_freestanding_compile(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj=Path(temporary)/'released.o'
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/pcie_released_windows.c'),'-o',str(obj)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            listing=subprocess.check_output(['xcrun','llvm-nm','--undefined-only',obj],text=True,timeout=30)
            self.assertEqual(listing.split(),['U','memcpy'])
if __name__=='__main__':unittest.main()
