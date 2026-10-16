# SPDX-License-Identifier: BSD-2-Clause
"""FIFO/VDM QoS models and register permissions, no board MMIO."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]


class PCIeQoSTests(unittest.TestCase):
    def native(self, name, sources):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / 'qos'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT / 'loader/rpi5'),
                '-I', str(ROOT / 'iokit/Kernel'), str(Path(__file__).with_name(name)),
                *map(str, sources), '-o', str(binary)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout

    def test_real_core_all_modes_all_callback_and_dependency_failures(self):
        self.assertEqual(self.native('pcie_qos_host.c', (ROOT / 'loader/rpi5/pcie_qos.c',)),
            b'PCIE_QOS_HOST_PASS CALLBACK_FAILURES=425 DEPENDENCY_FAILURES=425 NO_MMIO=1\n')

    def test_exact_phase_permissions_and_old_policies_unchanged(self):
        self.assertEqual(self.native('pcie_qos_policy_host.c', ()),
                         b'PCIE_QOS_POLICY_PASS READS=17 WRITES=13 NO_MMIO=1\n')


if __name__ == '__main__':
    unittest.main()
