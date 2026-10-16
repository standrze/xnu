# SPDX-License-Identifier: BSD-2-Clause
"""Actual full-FDT/QoS IOKit compilation and complete kernel linkage."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import build_pcie_profile_kernel as builder


class PCIeProfileKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'profile-kernel'
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_real_full_link_new_cores_and_every_protected_pin(self):
        r = self.report
        for key in ('complete_kernel_link_proven', 'original_fdt_options_checked_before_mapping',
                    'actual_fifo_vdm_qos_wired', 'same_owned_sessions', 'single_watchdog_claim'):
            self.assertTrue(r[key], key)
        for key in ('new_mapped_pages', 'initializer_runtime_executed', 'provider_personality_added',
                    'boot_caller_added', 'inherited_power_clock_shared_ownership_proven',
                    'physical_recovery_proven', 'rc_windows_link_wired', 'clkreq_aspm_programmed',
                    'irq_dma_authorized', 'installed', 'pi_executed', 'ethernet_proven',
                    'loader_package_created', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key], key)
        self.assertEqual(len(r['link']['profile_qos_implementations']), 4)
        self.assertEqual(len(r['link']['added_initializers']), 7)
        self.assertEqual(r['new_linker_warnings'], [])
        for row in r['compiles']:
            self.assertEqual(row['returncode'], 0); self.assertEqual(row['warning_count'], 0)
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_actual_preparation_orders_validation_before_ownership_and_requires_profile_opt_in(self):
        source = (self.output / 'overlay/BCM2712PCIePHYTransport.cpp').read_text()
        prepare = source[source.index('bool BCM2712PCIePHYTransport::prepare('):source.index('void BCM2712PCIePHYTransport::free()')]
        self.assertLess(prepare.index('rpi5_pcie_profile_decode'), prepare.index('phyOwner'))
        self.assertLess(prepare.index('rpi5_pcie_profile_decode'), prepare.index('provider->open(this)'))
        self.assertLess(prepare.index('rpi5_pcie_profile_decode'), prepare.index('mapBanks()'))
        self.assertIn('currentPhase == BCM2712_PHY_QOS_CONFIGURING', source)
        self.assertEqual(source.count('bcm2712_qos_access_allowed('), 2)
        self.assertIn('qos.state = RPI5_PCIE_QOS_QUARANTINED', source)
        args = [arg for arg in self.report['compiles'][0]['command'][:-2] if arg != '-c']
        result = subprocess.run(args + ['-URPI5_PCIE_PROFILE_QOS_DIAGNOSTIC', '-fsyntax-only'],
            cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Firmware profile/QoS', result.stderr)

    def test_receipt_drift_and_source_output_refused(self):
        with patch.object(builder, 'BASE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'receipt changed'): builder.inputs()
        with patch.object(builder, 'FIRMWARE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'firmware tree changed'): builder.inputs()
        for parent in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.BASE,
                       builder.audit.OBJ, builder.audit.SDK):
            output = parent / 'must-not-create-profile-kernel'
            with self.assertRaisesRegex(ValueError, 'separate fresh'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
