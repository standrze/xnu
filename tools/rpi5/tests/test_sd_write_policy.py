# SPDX-License-Identifier: BSD-2-Clause
"""Offline write admission only; no SD write command or kernel integration."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class SDWritePolicyTests(unittest.TestCase):
    def test_sanitized_admission_partition_bounds_epochs_and_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'write-policy'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                            '-I',str(ROOT/'iokit/Kernel'),
                            str(ROOT/'tools/rpi5/tests/sd_write_policy_host.c'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_write_policy.c'),'-o',str(binary)],check=True)
            fixture = ROOT/'build/rpi5/hfs-read-fixture-h9wpku5p/hfs-read.cdr'
            inputs = [[],[str(fixture)]] if fixture.is_file() else [[]]
            for args in inputs:
                result = subprocess.run([str(binary),*args],capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                self.assertEqual(result.stdout,b'SD_WRITE_POLICY_PASS\n')

    def test_dependency_free_freestanding_cortex_a76_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory)/'write-policy.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror','-c',
                            str(ROOT/'iokit/Kernel/rpi5_sd_write_policy.c'),'-o',str(obj)],check=True)
            undefined = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True)
            self.assertEqual(undefined,'')


if __name__ == '__main__':
    unittest.main()
