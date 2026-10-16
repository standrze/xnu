# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1BAR1ProbeTests(unittest.TestCase):
    def test_actual_config_and_bar_probe_faults_and_no_command_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            program=Path(temporary)/'bar'
            result=subprocess.run(['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE',
                '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                str(Path(__file__).with_name('rp1_bar1_probe_host.c')),
                str(ROOT/'loader/rpi5/pcie_config.c'),str(ROOT/'loader/rpi5/rp1_bar1_probe.c'),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_BAR1_PASS CONFIG_TRANSACTIONS=13 ENDPOINT_WRITES=2 CALLBACK_FAILURES=171 NO_HARDWARE=1\n')

    def test_a76_freestanding_compile(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/rp1_bar1_probe.c'),
                '-o',str(Path(temporary)/'bar.o')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
