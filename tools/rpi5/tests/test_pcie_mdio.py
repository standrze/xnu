# SPDX-License-Identifier: BSD-2-Clause
"""SerDes MDIO callback models and A76 compile, never electrical proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5.check_zsh_trial_package import profile_checks

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'loader/rpi5/pcie_mdio.c'


class PCIeMDIOTests(unittest.TestCase):
    def test_declaration_only_userland_profile_rejects_new_hardware_components(self):
        manifest = dict(gate5_pcie_topology=True, gate5_pcie_mmio_enabled=False,
                        gate4_storage_binding_snapshot=False, gate4_sd_readonly=False,
                        gate4_hfs_readonly=False, gate4_hfs_write_trial=False,
                        commands=[['clang', '-DRPI5_GATE5_PCIE_TOPOLOGY=1', 'probe_main.c'],
                                  ['clang', 'pcie_fdt.c'], ['clang', 'pcie_topology.c']])
        self.assertTrue(all(profile_checks(manifest).values()))
        for unit in ('pcie_mdio.c', 'pcie_rescal.c', 'pcie_serdes.c', 'pcie_reset.c'):
            with self.subTest(unit=unit):
                changed = {**manifest, 'commands': manifest['commands'] + [['clang', unit]]}
                self.assertFalse(profile_checks(changed)['no_hardware_observer_or_reset_objects'])

    def test_sanitized_both_done_polarities_deadlines_faults_and_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'mdio'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(CORE.parent),
                            str(Path(__file__).with_name('pcie_mdio_host.c')), str(CORE),
                            '-o', str(program)], check=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_MDIO_HOST_PASS\n')

    def test_freestanding_cortex_a76_no_external_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / 'mdio.o'
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                            '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                            '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-c', str(CORE), '-o', str(obj)], check=True, timeout=60)
            symbols = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', str(obj)],
                                              text=True, timeout=30)
            self.assertEqual(symbols.strip(), '')


if __name__ == '__main__':
    unittest.main()
