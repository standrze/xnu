# SPDX-License-Identifier: BSD-2-Clause
"""Serialized config core models + actual original-header bridge compile/link."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_apple_pci_config as builder

ROOT = Path(__file__).resolve().parents[3]
LOADER = ROOT / 'loader/rpi5'


class PCIeConfigTests(unittest.TestCase):
    def test_sanitized_failure_positions_w1c_subwords_bdfs_and_concurrent_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'config'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-D_DARWIN_C_SOURCE',
                            '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-I', str(LOADER), str(Path(__file__).with_name('pcie_config_host.c')),
                            str(LOADER / 'pcie_config.c'), '-o', str(program)],
                           check=True, capture_output=True, timeout=60)
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout,
                b'PCIE_CONFIG_HOST_PASS READS=14336 THREAD_READS=4000 FAILURE_POSITIONS=132 NO_MMIO=1\n')

    def test_freestanding_a76_core_has_no_undefined_runtime_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary) / 'config.o'
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                            '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding',
                            '-fno-builtin', '-fno-stack-protector', '-O2', '-Wall', '-Wextra',
                            '-Werror', '-c', str(LOADER / 'pcie_config.c'), '-o', str(obj)],
                           check=True, capture_output=True, timeout=60)
            self.assertEqual(subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', obj],
                                                    text=True, timeout=30).strip(), '')

    def test_original_apple_address_bitfields_execute_native_without_kernel_or_shims(self):
        builder.base_inputs()
        template = json.loads(builder.audit.TEMPLATE.read_text().strip().removesuffix(','))
        with tempfile.TemporaryDirectory() as temporary:
            obj, program = Path(temporary) / 'address.o', Path(temporary) / 'address'
            args = builder.command(template, Path(__file__).with_name('pcie_config_address_native.cpp'), obj)
            # Pure original-type/helper test on the host. Lower deployment only;
            # preserve real kernel headers/defines, never run any kernel API.
            args = ['--target=arm64-apple-macosx13.0.0' if arg.startswith('--target=') else
                    '-mmacos-version-min=13.0' if arg.startswith('-mmacos-version-min=') else arg
                    for arg in args]
            result = subprocess.run(args, cwd=template['directory'], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run(['xcrun', 'clang++', str(obj), '-Wl,-dead_strip', '-o', str(program)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_actual_abstract_bridge_and_family_link_retain_existing_dso_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertEqual(report['config_methods_compiled'], 6)
            self.assertEqual(report['maximum_transaction_callbacks'], 15)
            self.assertTrue(report['original_family_reused'])
            self.assertTrue(report['every_config_write_requires_provider_authorization'])
            self.assertEqual(report['link']['returncode'], 0)
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], ['___dso_handle'])
            for name, digest in report['inputs_sha256'].items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            self.assertEqual(builder.audit.sha(output / 'apple-bcm2712-pci-config.o'),
                             report['link']['object_sha256'])
            for name in ('concrete_provider_implemented', 'final_kernel_link_proven',
                         'hardware_access_enabled', 'driver_attachment_proven', 'pi_executed',
                         'bar_assignment_proven', 'dma_authorized', 'sd_actions',
                         'serial_actions', 'reboots', 'allocator_shim_used', 'fake_kernel_declarations_used'):
                self.assertFalse(report[name], name)
            for row in report['results']:
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(row['warning_count'], 0)
                self.assertEqual(builder.audit.sha(Path(row['log'])), row['log_sha256'])
            manifest = (output / 'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
            self.assertEqual(json.loads(manifest), report)

    def test_baseline_mutation_and_unsafe_output_rejected(self):
        with patch.object(builder, 'BASE_MANIFEST_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'compile manifest changed'):
                builder.base_inputs()
        for root in (builder.BASE, builder.audit.APPLE, builder.audit.OBJ, builder.audit.SDK):
            output = root / 'do-not-create-config-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside accepted'):
                builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
