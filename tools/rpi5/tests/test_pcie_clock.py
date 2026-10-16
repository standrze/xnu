# SPDX-License-Identifier: BSD-2-Clause
"""Native clock/advertisement core and exact transport permissions, no board access."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]


class PCIeClockTests(unittest.TestCase):
    def native(self, name, sources=()):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / 'clock'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT / 'loader/rpi5'),
                '-I', str(ROOT / 'iokit/Kernel'), str(Path(__file__).with_name(name)),
                *map(str, sources), '-o', str(binary)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout

    def test_real_core_modes_pre_and_post_link_failure_positions(self):
        self.assertEqual(self.native('pcie_clock_host.c', (ROOT / 'loader/rpi5/pcie_clock.c',)),
            b'PCIE_CLOCK_HOST_PASS CALLBACK_FAILURES=1124 DEPENDENCY_FAILURES=1124 READ_FAILURES=280 NO_MMIO=1\n')

    def test_exact_permissions_and_old_phases_unchanged(self):
        self.assertEqual(self.native('pcie_clock_policy_host.c'),
                         b'PCIE_CLOCK_POLICY_PASS READS=5 WRITES=1 NO_MMIO=1\n')


if __name__ == '__main__': unittest.main()
