# SPDX-License-Identifier: BSD-2-Clause
"""Actual IOKit continuation and complete-kernel link, not board execution."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_unused_kernel as builder


class PCIeUnusedKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'unused-kernel'
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_actual_warning_free_compile_full_link_and_protected_pins(self):
        r = self.report
        for name in ('complete_kernel_link_proven', 'actual_read_only_continuation_wired',
                     'same_owned_ubus_serdes_sessions', 'single_watchdog_claim'):
            self.assertTrue(r[name], name)
        for name in ('unused_windows_physically_observed', 'check_quiescent_provider_implemented',
                     'rc_windows_link_wired', 'irq_dma_authorized', 'power_clock_shared_ownership_proven',
                     'physical_recovery_proven', 'initializer_runtime_executed', 'provider_personality_added',
                     'boot_caller_added', 'installed', 'pi_executed', 'ethernet_proven', 'loader_package_created',
                     'sd_actions', 'serial_actions', 'reboots', 'new_inspection_writes', 'new_mapped_pages'):
            self.assertFalse(r[name], name)
        self.assertEqual(r['new_inspection_registers'], 23)
        self.assertEqual(len(r['link']['added_initializers']), 7)
        self.assertEqual(len(r['link']['unused_window_implementations']), 5)
        self.assertEqual(r['new_linker_warnings'], [])
        for row in r['compiles']:
            self.assertEqual(row['returncode'], 0)
            self.assertEqual(row['warning_count'], 0)
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        self.assertEqual(builder.audit.sha(Path(r['kernel'])), r['kernel_sha256'])
        self.assertNotIn(str(builder.full.COMPONENT),
                         (self.output / 'kernel.pcie-unused.filelist').read_text())
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_diagnostic_profile_required_and_real_owner_guard_retained(self):
        args = [arg for arg in self.report['compiles'][0]['command'][:-2] if arg != '-c']
        for flags, message in ((['-URPI5_PCIE_UNUSED_DIAGNOSTIC'], b'Unused-window inspection'),
                (['-URPI5_PCIE_UBUS_DIAGNOSTIC'], b'UBUS continuation'),
                (['-URPI5_PCIE_PHY_DIAGNOSTIC'], b'opt-in BCM2712'),
                (['-URPI5_FIRMWARE_FDT_HANDOFF'], b'Boot-FDT transport'),
                (['-UDEVELOPMENT', '-DDEVELOPMENT=0'], b'opt-in BCM2712')):
            result = subprocess.run(args + flags + ['-fsyntax-only'],
                cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)
        copied = (self.output / 'overlay/BCM2712PCIePHYTransport.cpp').read_text()
        self.assertIn('currentPhase == BCM2712_PHY_UNUSED_INSPECTING', copied)
        self.assertEqual(copied.count('bcm2712_unused_access_allowed('), 2)
        self.assertIn('unused.state = RPI5_PCIE_UNUSED_QUARANTINED', copied)
        self.assertIn('pe_rpi5_watchdog_check_pcie(this)', copied)

    def test_dependency_drift_and_source_output_refused(self):
        with patch.object(builder, 'BASE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'receipt changed'): builder.inputs()
        for parent in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.BASE,
                       builder.audit.OBJ, builder.audit.SDK):
            output = parent / 'must-not-create-unused-kernel'
            with self.assertRaisesRegex(ValueError, 'separate fresh'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
