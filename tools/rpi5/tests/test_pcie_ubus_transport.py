# SPDX-License-Identifier: BSD-2-Clause
"""Actual kernel UBUS continuation build and native boundary/failure models."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_ubus_transport as builder


class PCIeUBUSTransportTests(unittest.TestCase):
    def native(self, test, cores=()):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'test'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(builder.ROOT / 'iokit/Kernel'),
                '-I', str(builder.ROOT / 'loader/rpi5'), str(Path(__file__).with_name(test)),
                *(str(builder.ROOT / ('loader/rpi5/' + name + '.c')) for name in cores),
                '-o', str(program)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout

    def test_real_four_core_chain_both_axi_paths_and_every_guard_failure(self):
        self.assertEqual(self.native('pcie_ubus_chain_host.c',
            ('pcie_reset', 'pcie_rescal', 'pcie_mdio', 'pcie_serdes', 'pcie_ubus')),
            b'PCIE_UBUS_CHAIN_PASS GUARD_FAILURES=502 NO_MMIO=1\n')

    def test_new_phase_exact_permissions_and_old_policy_unchanged(self):
        self.assertEqual(self.native('pcie_ubus_policy_host.c'),
                         b'PCIE_UBUS_POLICY_PASS NEW_ACCESSES=11 NO_MMIO=1\n')

    def test_real_iokit_compile_partial_link_and_profile_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertEqual(report['actual_initial_cores_wired'],
                ['reset44', 'shared RESCAL', '54MHz SerDes/MDIO', 'UBUS/AXI'])
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], ['___dso_handle'])
            for name in ('actual_kernel_headers', 'actual_ubus_core_wired', 'same_owned_serdes_session',
                         'single_watchdog_claim', 'failure_quarantines_all_four_stages',
                         'output_committed_after_final_guard', 'no_new_mapped_pages', 'real_phase_restricted_mmio'):
                self.assertTrue(report[name], name)
            for name in ('original_sources_changed', 'installed', 'pi_executed', 'final_kernel_link_proven',
                         'power_clock_shared_ownership_proven', 'physical_recovery_proven',
                         'rc_windows_link_wired', 'config_bar_authorized', 'irq_dma_authorized',
                         'ethernet_proven', 'cleanup_mmio', 'sd_actions', 'serial_actions', 'reboots'):
                self.assertFalse(report[name], name)
            for name, digest in {**report['inputs_sha256'], **report['generated_sha256']}.items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            for row in report['results']:
                self.assertEqual(row['warning_count'], 0)
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(builder.audit.sha(Path(row['log'])), row['log_sha256'])
            manifest = (output / 'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
            command = [arg for arg in report['results'][0]['command'][:-2] if arg != '-c']
            for flags, message in ((['-URPI5_PCIE_UBUS_DIAGNOSTIC'], b'separate diagnostic build'),
                    (['-URPI5_PCIE_PHY_DIAGNOSTIC'], b'opt-in BCM2712 DEVELOPMENT build'),
                    (['-UDEVELOPMENT', '-DDEVELOPMENT=0'], b'opt-in BCM2712 DEVELOPMENT build'),
                    (['-UARM64_BOARD_CONFIG_BCM2712'], b'opt-in BCM2712 DEVELOPMENT build')):
                result = subprocess.run(command + flags + ['-fsyntax-only'],
                    cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
            asm = (output / 'transport.s').read_text()
            for instruction in ('dmb\tosh', 'dsb\tsy', '_pe_rpi5_watchdog_check_pcie',
                    '_rpi5_pcie_reset_pulse', '_rpi5_pcie_rescal_calibrate',
                    '_rpi5_pcie_serdes_configure54', '_rpi5_pcie_ubus_init', '_rpi5_pcie_ubus_configure'):
                self.assertIn(instruction, asm)

    def test_dependency_drift_and_unsafe_output_refused(self):
        with patch.object(builder, 'BASE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'Accepted PHY manifest changed'): builder.inputs()
        for root in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.audit.OBJ,
                     builder.audit.SDK, builder.BASE, builder.ROOT / 'build/rpi5/bl33-probe-vszhh6o4'):
            output = root / 'do-not-create-ubus-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
