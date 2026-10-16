# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1BarsProbeTests(unittest.TestCase):
    def test_actual_all_bar_core_and_config_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            program=Path(temporary)/'bars'
            result=subprocess.run(['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE',
                '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                str(Path(__file__).with_name('rp1_bars_probe_host.c')),
                str(ROOT/'loader/rpi5/pcie_config.c'),str(ROOT/'loader/rpi5/rp1_bars_probe.c'),
                str(ROOT/'loader/rpi5/rp1_bars_plan.c'),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_BARS_PASS CONFIG_TRANSACTIONS=49 ENDPOINT_WRITES=12 CALLBACK_FAILURES=649 ALL_SLOTS=6 NO_HARDWARE=1\n')

    def test_independent_allocation_arithmetic(self):
        with tempfile.TemporaryDirectory() as temporary:
            program=Path(temporary)/'plan'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                str(Path(__file__).with_name('rp1_bars_plan_host.c')),
                str(ROOT/'loader/rpi5/rp1_bars_plan.c'),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_BARS_PLAN_PASS LAYOUTS=4256 REJECTED=83 PURE_CANDIDATE=1 NO_HARDWARE=1\n')

    def test_a76_freestanding_compile(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ('rp1_bars_probe','rp1_bars_plan'):
                result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                    '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                    '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5'/(name+'.c')),
                    '-o',str(Path(temporary)/(name+'.o'))],capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
