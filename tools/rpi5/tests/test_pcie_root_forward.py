# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]


class RootForwardTests(unittest.TestCase):
    def test_actual_core_all_callbacks_sources_readbacks_and_restore(self):
        with tempfile.TemporaryDirectory(prefix='rpi5-root-forward-') as directory:
            exe=Path(directory)/'host'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(ROOT/'loader/rpi5'),str(Path(__file__).with_name('pcie_root_forward_host.c')),
                str(ROOT/'loader/rpi5/pcie_root_forward.c'),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertIn('ROOT_FORWARD_CORE_PASS READS=79 WRITES=4',result.stdout)

    def test_actual_a76_freestanding(self):
        with tempfile.TemporaryDirectory(prefix='rpi5-root-forward-a76-') as directory:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/pcie_root_forward.c'),
                '-o',str(Path(directory)/'root.o')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
