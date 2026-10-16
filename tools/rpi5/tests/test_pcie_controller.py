# SPDX-License-Identifier: BSD-2-Clause
"""Production controller methods against native models, not IOKit/board execution."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]


class PCIeControllerTests(unittest.TestCase):
    def test_actual_run_lifecycle_methods_with_real_cores_and_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            flags = ['-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                     '-I', str(ROOT/'loader/rpi5'), '-I', str(ROOT/'iokit/Kernel')]
            objects = []
            for name in ('pcie_ubus', 'pcie_unused', 'pcie_qos', 'pcie_clock', 'pcie_rc', 'pcie_windows', 'pcie_link'):
                obj = directory/(name+'.o'); objects.append(obj)
                subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',str(ROOT/'loader/rpi5'/ (name+'.c')),
                    '-o',str(obj)],check=True,capture_output=True,timeout=60)
            binary = directory/'controller'
            subprocess.run(['xcrun','clang++','-std=c++17',*flags,
                str(Path(__file__).with_name('pcie_controller_host.cpp')),*map(str,objects),'-o',str(binary)],
                check=True,capture_output=True,timeout=60)
            result = subprocess.run([str(binary)],capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,
                b'PCIE_CONTROLLER_HOST_PASS GUARD_FAILURES=12806 PROVIDER_FAILURES=12810 FRESH_CHECKS=12 NO_MMIO=1\n')

    def test_exact_three_new_phases_and_unchanged_old_policies(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary)/'policy'
            subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'iokit/Kernel'),
                str(Path(__file__).with_name('pcie_controller_policy_host.c')),'-o',str(binary)],
                check=True,capture_output=True,timeout=60)
            result = subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'PCIE_CONTROLLER_POLICY_PASS RC=50/26 LINK=31/4 CLOCK=7/2 NO_MMIO=1\n')


if __name__ == '__main__': unittest.main()
