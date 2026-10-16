# SPDX-License-Identifier: BSD-2-Clause
"""Actual IRQ/controller sequencing models and a distinct complete XNU link."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import build_pcie_irq_transport_kernel as builder


class PCIeIRQTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = (Path(cls.temporary.name) / 'irq-transport-kernel').resolve()
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_actual_initial_guard_pe_core_sequencing_models(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = (self.output / 'overlay' / builder.SOURCE_NAMES[0]).read_text()
            initial = source.split('bool BCM2712PCIePHYTransport::runInitialPHY(', 1)[1].split(
                '#include "BCM2712PCIeIRQTransport.inc"', 1)[0]
            (work / 'actual-irq-initial.inc').write_text('bool BCM2712PCIePHYTransport::runInitialPHY(' + initial)
            header = (self.output / 'overlay' / builder.SOURCE_NAMES[1]).read_text()
            observation = header.split('struct bcm2712_phy_observation {', 1)[1].split('};', 1)[0]
            (work / 'actual-irq-observation.inc').write_text('struct bcm2712_phy_observation {' + observation + '};\n')
            core = work / 'irq.o'
            common = ['-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-I', str(builder.ROOT)]
            subprocess.run(['xcrun', 'clang', '-std=c11', *common, '-c', str(builder.previous.CORE), '-o', str(core)],
                           check=True, capture_output=True, timeout=60)
            program = work / 'model'
            result = subprocess.run(['xcrun', 'clang++', '-std=c++17', *common,
                '-I', str(builder.ROOT / 'tools/rpi5/tests/pcie_irq_stubs'), '-I', str(work),
                str(Path(__file__).with_name('pcie_irq_transport_host.cpp')), str(core), '-o', str(program)],
                capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b'ACTUAL_INITIAL_GUARD_PE_CORE=1', result.stdout)
            self.assertIn(b'WATCHDOG_FAILURES=92 PROVIDER_FAILURES=15', result.stdout)
            self.assertIn(b'RESTORE_SUCCESS_ONLY=1 NO_MMIO=1', result.stdout)

    def test_real_complete_kernel_entries_dependencies_and_no_activation(self):
        r = self.report
        for key in ('complete_kernel_link_proven', 'single_watchdog_claim', 'irq_claim_after_watchdog_before_reset',
                    'real_xnu_interrupt_api', 'failed_irq_claim_leaves_local_interrupts_disabled',
                    'actual_irq_checks_bracket_lifecycle', 'same_owner_and_retained_thread',
                    'accepted_irq_pe_and_core_objects_reused', 'original_controller_entries_preserved', 'actual_halfword_mmio'):
            self.assertTrue(r[key], key)
        for key in ('concrete_lifecycle_provider_added', 'new_mapped_pages', 'initializer_runtime_executed',
                    'provider_personality_added', 'boot_caller_added', 'inherited_power_clock_shared_ownership_proven',
                    'physical_recovery_proven', 'irq_dma_authorized', 'installed', 'pi_executed', 'ethernet_proven',
                    'loader_package_created', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key], key)
        self.assertEqual(len(r['link']['controller_irq_implementations']), 18)
        self.assertEqual(len(r['link']['added_initializers']), 7)
        self.assertEqual(r['new_linker_warnings'], [])
        self.assertEqual(len(r['compiles']), 1)
        self.assertEqual(r['compiles'][0]['warning_count'], 0)
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        # The complete kernel reuses actual PE/IRQ cores, never substitutes
        # the host doubles or duplicates their definitions.
        objects = (self.output / 'kernel.pcie-irq-transport.filelist').read_text().splitlines()
        prior = (builder.BASE / 'kernel.pcie-irq.filelist').read_text().splitlines()
        self.assertEqual(set(prior)-{str(builder.REPLACED)}, set(objects)-{str(self.output / (builder.SOURCE_NAMES[0]+'.o'))})
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_actual_calls_opt_in_and_initial_sequencing(self):
        source = (self.output / 'overlay' / builder.SOURCE_NAMES[0]).read_text()
        initial = source.split('bool BCM2712PCIePHYTransport::runInitialPHY(', 1)[1]
        ordered = ('retain();', 'claimAttempted = true', 'pe_rpi5_watchdog_claim_pcie',
                   'claimControllerIRQ', 'rpi5_pcie_reset_init', 'rpi5_pcie_reset_pulse',
                   'rpi5_pcie_rescal_init', 'rpi5_pcie_serdes_configure54', '*out = result')
        positions = [initial.index(part) for part in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(source.count('pe_rpi5_watchdog_claim_pcie('), 1)
        body = builder.BODY.read_text()
        self.assertNotIn('__asm__', body)
        self.assertEqual(body.count('pe_rpi5_pcie_irq_check(this, &observed)'), 2)
        assembly = (self.output / 'transport.s').read_text()
        for call in ('_ml_set_interrupts_enabled', '_pe_rpi5_pcie_irq_claim', '_pe_rpi5_pcie_irq_check'):
            self.assertIn(call, assembly)
        args = [arg for arg in self.report['compiles'][0]['command'][:-2] if arg != '-c']
        result = subprocess.run(args+['-URPI5_PCIE_IRQ_TRANSPORT', '-fsyntax-only'],
            cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'PCIe IRQ transport requires', result.stderr)

    def test_preserved_receipt_and_unsafe_outputs_refused(self):
        with patch.object(builder, 'BASE_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'Accepted IRQ receipt changed'): builder.inputs()
        for parent in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.BASE, builder.CONTROLLER,
                       builder.audit.OBJ, builder.audit.SDK):
            out = parent / 'must-not-create-irq-transport'
            with self.assertRaisesRegex(ValueError, 'separate fresh'): builder.build(out)
            self.assertFalse(out.exists())


if __name__ == '__main__': unittest.main()
