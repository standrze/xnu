# SPDX-License-Identifier: BSD-2-Clause
"""Actual kernel compile plus native transport-policy boundaries; no board I/O."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_phy_transport as builder


class PCIePHYTransportTests(unittest.TestCase):
    def test_real_three_core_chain_with_transport_policy_and_guard_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'chain'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(builder.ROOT / 'iokit/Kernel'),
                '-I', str(builder.ROOT / 'loader/rpi5'),
                str(Path(__file__).with_name('pcie_phy_chain_host.c')),
                *(str(builder.ROOT / ('loader/rpi5/' + name + '.c')) for name in
                  ('pcie_reset', 'pcie_rescal', 'pcie_mdio', 'pcie_serdes')),
                '-o', str(program)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_PHY_CHAIN_PASS GUARD_FAILURES=206 NO_MMIO=1\n')

    def test_sanitized_exact_mapping_and_exhaustive_access_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'policy'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(builder.ROOT / 'iokit/Kernel'),
                str(Path(__file__).with_name('pcie_phy_policy_host.c')), '-o', str(program)],
                check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_PHY_POLICY_PASS ACCEPTED_ACCESSES=15 NO_MMIO=1\n')

    def test_actual_iokit_compile_and_combined_pci_watchdog_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertEqual(report['actual_initial_cores_wired'], ['reset44', 'shared RESCAL', '54MHz SerDes/MDIO'])
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], ['___dso_handle'])
            self.assertEqual(report['mapped_page_bytes'], [0xc000, 0x4000, 0x4000])
            for key in ('actual_kernel_headers', 'actual_mmio_transport_implemented',
                        'actual_fdt_decoder_reused', 'phases_restrict_register_offsets',
                        'watchdog_guard_before_and_after_mmio', 'ownership_retained_after_claim_failure',
                        'rounded_pages_require_immutable_device_classification'):
                self.assertTrue(report[key], key)
            for key in ('installed', 'pi_executed', 'final_kernel_link_proven', 'ethernet_proven',
                        'shared_power_clock_admission_proven', 'provider_open_proves_hardware_exclusivity',
                        'physical_reset_timing_proven', 'reset_destination_proven', 'link_training_wired',
                        'concrete_pci_bridge_owner_implemented', 'dma_authorized', 'registry_boolean_admission_used',
                        'fake_kernel_declarations_used', 'cleanup_mmio', 'power_off', 'sd_actions', 'serial_actions', 'reboots'):
                self.assertFalse(report[key], key)
            for name, digest in report['inputs_sha256'].items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            for row in report['results']:
                self.assertEqual(row['warning_count'], 0)
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(builder.audit.sha(Path(row['log'])), row['log_sha256'])
            self.assertEqual(builder.audit.sha(output / 'apple-bcm2712-pcie-phy-diagnostic.o'),
                             report['link']['object_sha256'])
            manifest = (output / 'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
            command = [arg for arg in report['results'][0]['command'][:-2] if arg != '-c']
            for flags in (['-URPI5_PCIE_PHY_DIAGNOSTIC'], ['-UDEVELOPMENT', '-DDEVELOPMENT=0'],
                          ['-UARM64_BOARD_CONFIG_BCM2712']):
                result = subprocess.run(command + flags + ['-fsyntax-only'],
                    cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'opt-in BCM2712 DEVELOPMENT build', result.stderr)
            # Retain actual target assembly as inspection evidence, not simulated
            # hardware. No mocked IOKit/PM declarations or replacement core.
            assembly = output / 'transport.s'
            self.assertEqual(report['assembly_result']['returncode'], 0)
            self.assertEqual(builder.audit.sha(assembly), report['generated_sha256'][str(assembly.resolve())])
            asm = assembly.read_text()
            self.assertIn('dmb\tosh', asm)
            self.assertIn('dsb\tsy', asm)
            self.assertIn('_pe_rpi5_watchdog_check_pcie', asm)
            self.assertIn('_rpi5_pcie_reset_pulse', asm)
            self.assertIn('_rpi5_pcie_rescal_calibrate', asm)
            self.assertIn('_rpi5_pcie_serdes_configure54', asm)

    def test_changed_dependencies_and_unsafe_output_refused(self):
        wrong = tuple((directory, '0'*64, obj) for directory, _, obj in builder.BASELINES)
        with patch.object(builder, 'BASELINES', wrong):
            with self.assertRaisesRegex(ValueError, 'dependency manifest changed'): builder.inputs()
        for root in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.audit.OBJ,
                     builder.audit.SDK, *(directory for directory, _, _ in builder.BASELINES)):
            output = root / 'do-not-create-phy-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
