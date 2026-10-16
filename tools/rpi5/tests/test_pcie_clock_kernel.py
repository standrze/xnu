# SPDX-License-Identifier: BSD-2-Clause
"""Real IOKit pre-link clock wiring and complete kernel linkage, no Pi actions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import build_pcie_clock_kernel as builder


class PCIeClockKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'clock-kernel'
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_actual_full_link_owned_prelink_and_all_pins(self):
        r = self.report
        for key in ('complete_kernel_link_proven', 'original_fdt_options_checked_before_mapping',
                    'actual_fifo_vdm_qos_wired', 'actual_aspm_prelink_wired',
                    'postlink_clock_core_compiled', 'same_owned_sessions', 'single_watchdog_claim'):
            self.assertTrue(r[key], key)
        for key in ('postlink_clkreq_wired', 'rc_windows_link_wired', 'new_mapped_pages',
                    'initializer_runtime_executed', 'provider_personality_added', 'boot_caller_added',
                    'inherited_power_clock_shared_ownership_proven', 'physical_recovery_proven',
                    'clkreq_aspm_programmed', 'irq_dma_authorized', 'installed', 'pi_executed',
                    'ethernet_proven', 'loader_package_created', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key], key)
        self.assertEqual(len(r['link']['clock_implementations']), 4)
        self.assertEqual(len(r['link']['added_initializers']), 7)
        self.assertEqual(r['new_linker_warnings'], [])
        for row in r['compiles']:
            self.assertEqual(row['returncode'], 0); self.assertEqual(row['warning_count'], 0)
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_actual_transport_stage_calls_and_opt_in(self):
        source = (self.output / 'overlay/BCM2712PCIePHYTransport.cpp').read_text()
        self.assertIn('currentPhase == BCM2712_PHY_CLOCK_PREPARING', source)
        self.assertEqual(source.count('bcm2712_clock_access_allowed('), 2)
        self.assertIn('clockPolicy.state = RPI5_PCIE_CLOCK_QUARANTINED', source)
        entry = (builder.ROOT / 'iokit/Kernel/BCM2712PCIeClock.inc').read_text()
        self.assertLess(entry.index('runPHYUBUSWindowAndQoS(&result.prior)'),
                        entry.index('rpi5_pcie_clock_init(&clockPolicy, &qos)'))
        self.assertLess(entry.index('rpi5_pcie_clock_init'), entry.index('rpi5_pcie_clock_prepare'))
        self.assertLess(entry.index('rpi5_pcie_clock_prepare'), entry.index('*out = result'))
        self.assertNotIn('RPI5_PCIE_LINK_COMPLETE', entry)
        self.assertNotIn('rpi5_pcie_clock_finish(', entry)
        args = [arg for arg in self.report['compiles'][0]['command'][:-2] if arg != '-c']
        result = subprocess.run(args + ['-URPI5_PCIE_CLOCK_DIAGNOSTIC', '-fsyntax-only'],
            cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'PCIe clock advertisement', result.stderr)

    def test_receipt_drift_and_protected_output_refused(self):
        with patch.object(builder, 'BASE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'receipt changed'): builder.inputs()
        for parent in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.BASE,
                       builder.audit.OBJ, builder.audit.SDK):
            output = parent / 'must-not-create-clock-kernel'
            with self.assertRaisesRegex(ValueError, 'separate fresh'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
