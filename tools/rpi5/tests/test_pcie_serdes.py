# SPDX-License-Identifier: BSD-2-Clause
"""Actual MDIO-core integration under models; not hardware bring-up."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'loader/rpi5/pcie_serdes.c'
MDIO = CORE.with_name('pcie_mdio.c')


class PCIeSerdesTests(unittest.TestCase):
    def test_sanitized_fixed_profile_dependency_and_every_callback_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'serdes'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(CORE.parent),
                            str(Path(__file__).with_name('pcie_serdes_host.c')), str(CORE), str(MDIO),
                            '-o', str(program)], check=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_SERDES_HOST_PASS\n')

    def test_freestanding_cortex_a76_links_with_only_mdio_no_other_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            objects = []
            for source in (CORE, MDIO):
                obj = Path(directory) / (source.stem + '.o')
                subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                                '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                                '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror',
                                '-c', str(source), '-o', str(obj)], check=True, timeout=60)
                objects.append(str(obj))
            combined = Path(directory) / 'combined.o'
            subprocess.run([str(ROOT / 'tools/rpi5/tfa-lld'), '-r', '-o', str(combined), *objects],
                           check=True, timeout=30)
            symbols = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', str(combined)],
                                              text=True, timeout=30)
            self.assertEqual(symbols.strip(), '')


if __name__ == '__main__':
    unittest.main()
