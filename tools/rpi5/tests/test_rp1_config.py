# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1ConfigTests(unittest.TestCase):
    def test_production_transport_runs_and_stops_after_every_guard_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            objects=[]
            for source in ('pcie_config','rp1_config_snapshot'):
                obj=Path(temporary)/(source+'.o')
                result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-c',str(ROOT/'loader/rpi5'/(source+'.c')),'-o',str(obj)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr);objects.append(obj)
            program=Path(temporary)/'transport'
            result=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),
                str(Path(__file__).with_name('rp1_transport_host.cpp')),*map(str,objects),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertRegex(result.stdout,r'^RP1_TRANSPORT_PASS ACTUAL_METHODS=7 GUARD_FAILURES=\d+ NO_HARDWARE=1\n$')

    def test_actual_config_and_snapshot_failures_and_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            program=Path(temporary)/'rp1'
            args=['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE','-Wall','-Wextra','-Werror',
                  '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),
                  str(Path(__file__).with_name('rp1_config_host.c')),
                  str(ROOT/'loader/rpi5/pcie_config.c'),str(ROOT/'loader/rpi5/rp1_config_snapshot.c'),'-o',str(program)]
            result=subprocess.run(args,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_CONFIG_PASS READS=32 SELECTOR_WRITES=32 ENDPOINT_WRITES=0 FAILURES=416 MUTATIONS=16 NO_HARDWARE=1\n')

    def test_a76_snapshot_uses_config_core_and_standard_kernel_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj=Path(temporary)/'snapshot.o'
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/rp1_config_snapshot.c'),'-o',str(obj)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            names=subprocess.check_output(['xcrun','llvm-nm','--undefined-only',obj],text=True,timeout=30)
            self.assertEqual(names.split(),['U','memcpy','U','memset','U','rpi5_pcie_config_transfer'])


if __name__=='__main__':unittest.main()
