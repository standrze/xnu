# SPDX-License-Identifier: BSD-2-Clause
"""Original-type resource translation and actual Apple API compilation; no MMIO."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_apple_pci_resources as builder


class ApplePCIResourceTests(unittest.TestCase):
    def test_original_type_address_translation_boundaries_and_transactional_failure(self):
        builder.inputs()
        template = json.loads(builder.audit.TEMPLATE.read_text().strip().removesuffix(','))
        with tempfile.TemporaryDirectory() as temporary:
            obj, program = Path(temporary) / 'resources.o', Path(temporary) / 'resources'
            args = builder.config.command(template, Path(__file__).with_name('pcie_resource_address_native.cpp'), obj)
            args = ['--target=arm64-apple-macosx13.0.0' if arg.startswith('--target=') else
                    '-mmacos-version-min=13.0' if arg.startswith('-mmacos-version-min=') else arg
                    for arg in args]
            result = subprocess.run(args, cwd=template['directory'], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run(['xcrun', 'clang++', str(obj), '-Wl,-dead_strip', '-o', str(program)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run([str(program)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, 'failed native source line modulo 256: ' + str(result.returncode))

    def test_actual_api_compile_family_link_and_input_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertTrue(report['original_family_reused'])
            self.assertTrue(report['live_owner_admission_required'])
            self.assertTrue(report['original_zero_base_assignment_publication_fixed'])
            self.assertTrue(report['original_64bit_assignment_tag_publication_fixed'])
            self.assertEqual(report['adapted_units'], ['IOPCIConfigurator.cpp'])
            self.assertEqual(report['adaptation']['returncode'], 0)
            self.assertEqual(report['allocator_address_space'], 'PCI bus')
            self.assertEqual(report['descriptor_address_space'], 'CPU physical')
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], ['___dso_handle'])
            for name, digest in report['inputs_sha256'].items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            self.assertEqual(builder.audit.sha(output / 'apple-bcm2712-pci-resources.o'),
                             report['link']['object_sha256'])
            for name in ('concrete_provider_implemented', 'final_kernel_link_proven',
                         'hardware_access_enabled', 'driver_attachment_proven', 'pi_executed',
                         'bar_assignment_proven', 'dma_authorized', 'sd_actions', 'serial_actions',
                         'reboots', 'decode_padding_allocatable', 'allocator_shim_used',
                         'fake_kernel_declarations_used'):
                self.assertFalse(report[name], name)
            for row in report['results']:
                self.assertEqual(row['returncode'], 0)
                if Path(row['command'][-1]).name != 'IOPCIConfigurator.cpp.o':
                    self.assertEqual(row['warning_count'], 0)
                self.assertEqual(builder.audit.sha(Path(row['log'])), row['log_sha256'])
            manifest = (output / 'manifest.json').read_bytes()
            self.assertEqual(json.loads(manifest), report)
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
            adapted = next(row for row in report['results'] if
                           Path(row['command'][-1]).name == 'IOPCIConfigurator.cpp.o')
            rejected = subprocess.run(adapted['command'][:-2] +
                ['-UARM64_BOARD_CONFIG_BCM2712', '-fsyntax-only'],
                cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b'restricted to BCM2712', rejected.stderr)

    def test_opt_out_preprocessed_configurator_matches_preserved_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            adapted = next(row for row in report['results'] if
                           Path(row['command'][-1]).name == 'IOPCIConfigurator.cpp.o')
            args = [arg for arg in adapted['command'][:-2] if arg not in
                    ('-c', '-DRPI5_PCI_CPU_TRANSLATED_RESOURCES=1')]
            # Compare code, not two wall-clock expansions that can cross a
            # second/day boundary. Actual build flags are unchanged.
            args += ['-E', '-P', '-Wno-builtin-macro-redefined',
                     '-D__TIME__="00:00:00"', '-D__DATE__="Jan 01 2000"']
            result = subprocess.run(args, cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT',
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            args = [str(builder.config.BASE / 'IOPCIFamily-adapted/IOPCIConfigurator.cpp')
                    if arg == str(output / 'IOPCIConfigurator.cpp') else arg for arg in args]
            original = subprocess.run(args, cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT',
                                      capture_output=True, timeout=60)
            self.assertEqual(original.returncode, 0, original.stderr.decode())
            normalized = lambda data: [line.strip() for line in data.splitlines() if line.strip()]
            self.assertEqual(normalized(result.stdout), normalized(original.stdout))

    def test_changed_baseline_and_unsafe_destination_rejected(self):
        with patch.object(builder, 'MANIFEST_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'config manifest changed'):
                builder.inputs()
        for root in (builder.BASE, builder.config.BASE, builder.audit.APPLE, builder.audit.OBJ, builder.audit.SDK):
            output = root / 'do-not-create-resource-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside accepted'):
                builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
