# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class GEMIdentifyTests(unittest.TestCase):
    def test_actual_core_faults_and_clock_profile(self):
        with tempfile.TemporaryDirectory(prefix='rp1-gem-core-') as directory:
            exe=Path(directory)/'host'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                str(Path(__file__).with_name('rp1_gem_identify_host.c')),
                str(ROOT/'loader/rpi5/rp1_gem_identify.c'),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertRegex(result.stdout,r'RP1_GEM_IDENTIFY_PASS READS=32 FAULTS=\d+ DIVIDER_CASES=960 NO_WRITES=1 NO_HARDWARE=1')

    def test_a76_freestanding_object(self):
        with tempfile.TemporaryDirectory(prefix='rp1-gem-target-') as directory:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/rp1_gem_identify.c'),
                '-o',str(Path(directory)/'gem.o')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
