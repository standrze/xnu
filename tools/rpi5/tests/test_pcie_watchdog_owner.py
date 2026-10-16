# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_watchdog_owner as builder


class PCIeWatchdogOwnerTests(unittest.TestCase):
    def test_sanitized_lease_failure_budget_and_real_mutex_interleaving(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'lease'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(builder.ROOT / 'loader/rpi5'),
                str(Path(__file__).with_name('pcie_watchdog_host.c')), str(builder.CORE),
                '-o', str(program)], check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b'PCIE_WATCHDOG_HOST_PASS FAILURE_POSITIONS=12 '
                b'CHECK_LIMIT=65536 THREAD_ATTEMPTS=120000 NO_MMIO=1\n')

    def test_freestanding_a76_core_has_no_undefined_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary) / 'lease.o'
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror', '-c',
                str(builder.CORE), '-o', str(obj)], check=True, capture_output=True, timeout=60)
            self.assertEqual(builder.audit.read_command(['xcrun', 'llvm-nm', '--undefined-only', obj]), '')

    def test_actual_kernel_owner_compiles_links_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertTrue(report['actual_xnu_pm_mapping_reused'])
            self.assertTrue(report['normal_servicing_suppressed_after_claim'])
            self.assertTrue(report['claim_nonblocking'])
            self.assertEqual(report['watchdog_countdown_writes_per_lease'], 1)
            self.assertEqual(report['access_deadline_seconds'], 12)
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], [])
            for name, digest in report['inputs_sha256'].items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            for row in report['results']:
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(row['warning_count'], 0)
                self.assertEqual(builder.audit.sha(Path(row['log'])), row['log_sha256'])
            restricted = [arg for arg in report['results'][0]['command'][:-2] if arg != '-c'] + [
                '-UDEVELOPMENT', '-DDEVELOPMENT=0', '-fsyntax-only']
            result = subprocess.run(restricted, cwd=builder.audit.OBJ / 'pexpert/DEVELOPMENT',
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'opt-in BCM2712 DEVELOPMENT build', result.stderr)
            for key in ('final_kernel_link_proven', 'installed', 'pi_executed',
                        'physical_reset_timing_proven', 'reset_destination_proven',
                        'concrete_pci_provider_implemented', 'dma_authorized',
                        'cancel_or_release_implemented', 'sd_actions', 'serial_actions', 'reboots',
                        'reset_route_writes', 'reset_status_writes'):
                self.assertFalse(report[key], key)
            manifest = (output / 'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)

    def test_disabled_patch_preprocessing_matches_current_pe_fiq(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            builder.build(output)
            template = json.loads(builder.TEMPLATE.read_text().strip().removesuffix(','))
            args = builder.command(template, output / 'pe_fiq.c', output / 'unused.o', enabled=False)
            args = [arg for arg in args[:-2] if arg != '-c'] + ['-E', '-P',
                '-Wno-builtin-macro-redefined', '-D__TIME__="00:00:00"', '-D__DATE__="Jan 01 2000"']
            adapted = subprocess.run(args, cwd=template['directory'], capture_output=True, timeout=60)
            self.assertEqual(adapted.returncode, 0, adapted.stderr.decode())
            args = [str(builder.SOURCE) if arg == str(output / 'pe_fiq.c') else arg for arg in args]
            original = subprocess.run(args, cwd=template['directory'], capture_output=True, timeout=60)
            self.assertEqual(original.returncode, 0, original.stderr.decode())
            normalize = lambda data: [line.strip() for line in data.splitlines() if line.strip()]
            self.assertEqual(normalize(adapted.stdout), normalize(original.stdout))

    def test_changed_pins_and_unsafe_output_refused(self):
        with patch.object(builder, 'SOURCE_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'pe_fiq source changed'): builder.inputs()
        with patch.object(builder, 'TEMPLATE_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'compile template changed'): builder.inputs()
        for root in (builder.audit.OBJ, builder.audit.SDK, builder.ROOT / 'pexpert', builder.ROOT / 'loader'):
            output = root / 'do-not-create-watchdog-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
