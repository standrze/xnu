# SPDX-License-Identifier: BSD-2-Clause
"""Shared calibration callback models and cross-compile, not hardware proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'loader/rpi5/pcie_rescal.c'


class PCIeRescalTests(unittest.TestCase):
    def test_sanitized_order_deadlines_every_callback_failure_and_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'rescal'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(CORE.parent),
                            str(Path(__file__).with_name('pcie_rescal_host.c')), str(CORE),
                            '-o', str(program)], check=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_RESCAL_HOST_PASS\n')

    def test_freestanding_cortex_a76_no_external_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / 'rescal.o'
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                            '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                            '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-c', str(CORE), '-o', str(obj)], check=True, timeout=60)
            symbols = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', str(obj)],
                                              text=True, timeout=30)
            self.assertEqual(symbols.strip(), '')


if __name__ == '__main__':
    unittest.main()
