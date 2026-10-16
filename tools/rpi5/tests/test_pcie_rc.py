# SPDX-License-Identifier: BSD-2-Clause
"""RC/window/UBUS/link composition models, not physical controller evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
LOADER = ROOT / 'loader/rpi5'
CORES = ('pcie_rc.c', 'pcie_windows.c', 'pcie_ubus.c', 'pcie_link.c')


class PCIeRCTests(unittest.TestCase):
    def test_sanitized_failures_and_real_core_composition(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'rc'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(LOADER),
                            str(Path(__file__).with_name('pcie_rc_host.c')),
                            *(str(LOADER / source) for source in CORES), '-o', str(program)],
                           check=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout,
                             b'PCIE_RC_HOST_PASS FAILURE_POSITIONS=146 COMPOSED=RC_WINDOWS_UBUS_LINK\n')

    def test_freestanding_a76_composed_link_has_no_undefined_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            objects = []
            for source in CORES:
                obj = Path(temporary) / (source + '.o')
                subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                                '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding',
                                '-fno-builtin', '-fno-stack-protector', '-O2', '-Wall', '-Wextra',
                                '-Werror', '-c', str(LOADER / source), '-o', str(obj)],
                               check=True, timeout=60)
                objects.append(obj)
            linker = ROOT / 'tools/rpi5/tfa-lld'
            linked = Path(temporary) / 'composed.o'
            subprocess.run([str(linker), '-r', *(str(obj) for obj in objects), '-o', str(linked)],
                           check=True, timeout=60)
            symbols = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', str(linked)],
                                              text=True, timeout=30)
            self.assertEqual(symbols.strip(), '')


if __name__ == '__main__':
    unittest.main()
