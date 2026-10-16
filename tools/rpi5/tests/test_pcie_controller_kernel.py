# SPDX-License-Identifier: BSD-2-Clause
"""Actual controller transport/MMIO and complete-kernel integration, no board actions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import build_pcie_controller_kernel as builder


class PCIeControllerKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name)/'controller-kernel'
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_actual_complete_link_all_core_entries_and_pins(self):
        r = self.report
        for key in ('complete_kernel_link_proven', 'actual_fifo_vdm_qos_wired',
                    'actual_aspm_prelink_wired', 'postlink_clkreq_wired', 'rc_windows_link_wired',
                    'independent_provider_callback_required', 'fresh_unused_rechecks_wired',
                    'actual_halfword_mmio', 'guarded_link_delay_chunks', 'same_owned_sessions', 'single_watchdog_claim'):
            self.assertTrue(r[key],key)
        for key in ('concrete_lifecycle_provider_added', 'new_mapped_pages', 'initializer_runtime_executed',
                    'provider_personality_added', 'boot_caller_added', 'inherited_power_clock_shared_ownership_proven',
                    'physical_recovery_proven', 'clkreq_aspm_programmed', 'irq_dma_authorized', 'installed',
                    'pi_executed', 'ethernet_proven', 'loader_package_created', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key],key)
        self.assertEqual(len(r['link']['controller_implementations']),12)
        self.assertEqual(len(r['link']['added_initializers']),7)
        self.assertEqual(r['new_linker_warnings'],[])
        self.assertEqual(len(r['compiles']),3)
        for row in r['compiles']:
            self.assertEqual(row['returncode'],0); self.assertEqual(row['warning_count'],0)
        for name,digest in {**r['inputs_sha256'],**r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)),digest,name)
        before = (self.output/'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before,(self.output/'manifest.json').read_bytes())

    def test_actual_owner_checks_halfwords_transition_delay_and_opt_in(self):
        source = (self.output/'overlay/BCM2712PCIePHYTransport.cpp').read_text()
        guard = source[source.index('bool BCM2712PCIePHYTransport::guard()'):source.index('bool BCM2712PCIePHYTransport::mapBanks()')]
        self.assertIn('controllerAdmission.check(ownerProvider, lifecyclePhase)',guard)
        self.assertIn('checkingLifecycle',guard)
        self.assertIn('getPhase() != currentPhase',guard)
        self.assertEqual(source.count('bcm2712_controller_access_allowed('),2)
        self.assertIn('us > 100000',source); self.assertIn('us > 1000 ? 1000 : us',source)
        self.assertIn('lifecyclePhase = BCM2712_CONTROLLER_RELEASED',source)
        initial = source[source.index('bool BCM2712PCIePHYTransport::runInitialPHY('):]
        self.assertLess(initial.index('controllerMode && checkingLifecycle'),initial.index('retain();'))
        entry = (builder.ROOT/'iokit/Kernel/BCM2712PCIeControllerRun.inc').read_text()
        ordered = ('controllerAdmission.check(ownerProvider, lifecyclePhase)', 'runPHYUBUSQoSAndClock',
            'rpi5_pcie_windows_init', 'rpi5_pcie_rc_init', 'rpi5_pcie_rc_configure',
            'rpi5_pcie_link_init', 'rpi5_pcie_link_train', 'rpi5_pcie_clock_finish', '*out = result')
        positions = [entry.index(part) for part in ordered]
        self.assertEqual(positions,sorted(positions))
        self.assertNotIn('.state = RPI5_PCIE_',entry)
        assembly = (self.output/'transport.s').read_text()
        for fragment,op in (('controllerRead16','ldrh'),('controllerWrite16','strh')):
            name = next(n for n in self.report['link']['controller_implementations'] if fragment in n)
            body = assembly.split(name+':',1)[1].split('\n\t.globl',1)[0]
            self.assertIn('\t'+op+'\t',body)
            self.assertIn('dmb\tosh',body); self.assertIn('dsb\tsy',body)
        args = [arg for arg in self.report['compiles'][0]['command'][:-2] if arg != '-c']
        result = subprocess.run(args+['-URPI5_PCIE_CONTROLLER_DIAGNOSTIC','-fsyntax-only'],
            cwd=builder.audit.OBJ/'iokit/DEVELOPMENT',capture_output=True,timeout=60)
        self.assertNotEqual(result.returncode,0); self.assertIn(b'PCIe controller composition',result.stderr)

    def test_receipt_drift_and_protected_outputs_refused(self):
        with patch.object(builder,'BASE_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'receipt changed'): builder.inputs()
        for parent in (builder.ROOT/'iokit',builder.ROOT/'loader',builder.BASE,builder.audit.OBJ,builder.audit.SDK):
            output = parent/'must-not-create-controller-kernel'
            with self.assertRaisesRegex(ValueError,'separate fresh'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
