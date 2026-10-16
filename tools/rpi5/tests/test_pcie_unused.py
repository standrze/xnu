# SPDX-License-Identifier: BSD-2-Clause
"""Read-only window prerequisite models; not physical controller evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'loader/rpi5/pcie_unused.c'


class PCIeUnusedTests(unittest.TestCase):
    def native(self, name, cores):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'unused'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(CORE.parent),
                '-I', str(ROOT / 'iokit/Kernel'), str(Path(__file__).with_name(name)),
                *map(str, cores), '-o', str(program)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout

    def test_sanitized_disabled_windows_drift_and_all_callback_failures(self):
        self.assertEqual(self.native('pcie_unused_host.c', (CORE,)),
            b'PCIE_UNUSED_HOST_PASS CALLBACK_FAILURES=139 READ_FAILURES=46 DEPENDENCY_FAILURES=139 NO_MMIO=1\n')

    def test_exact_read_only_permissions_and_prior_policy_unchanged(self):
        self.assertEqual(self.native('pcie_unused_policy_host.c', ()),
            b'PCIE_UNUSED_POLICY_PASS NEW_READS=23 NEW_WRITES=0 NO_MMIO=1\n')

    def test_freestanding_a76_only_standard_kernel_copy_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary) / 'unused.o'
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror', '-c', str(CORE),
                '-o', str(obj)], check=True, capture_output=True, timeout=60)
            listing = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', str(obj)],
                                             text=True, timeout=30)
            # Clang lowers the observation-sized publication to memcpy. The real
            # XNU final-link test must resolve this to its existing implementation.
            self.assertEqual(listing.strip(), 'U memcpy')


if __name__ == '__main__':
    unittest.main()
