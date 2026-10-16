# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]


class PHYResetCycleTests(unittest.TestCase):
    def test_actual_core_all_failure_boundaries_and_a76(self):
        with tempfile.TemporaryDirectory(prefix='phy-reset-cycle-') as name:
            folder=Path(name);core=ROOT/'loader/rpi5/rp1_phy_reset_cycle.c'
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'loader/rpi5')]
            exe=folder/'host'
            r=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',str(Path(__file__).with_name('rp1_phy_reset_cycle_host.c')),
                str(core),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=30);self.assertEqual(r.returncode,0,r.stderr);print(r.stdout,end='')
            self.assertIn('READS=19 WRITES=12 OTHER_PINS_PRESERVED=1 NO_HARDWARE=1',r.stdout)
            r=subprocess.run(['xcrun','clang',*flags,'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
                '-mgeneral-regs-only','-ffreestanding','-fno-builtin','-O2','-c',str(core),'-o',str(folder/'core.o')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':unittest.main()
