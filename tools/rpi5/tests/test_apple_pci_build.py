# SPDX-License-Identifier: BSD-2-Clause
"""Real-header Apple PCI compile screens, not driver/runtime acceptance."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import audit_apple_pci_build as audit


class ApplePCIBuildTests(unittest.TestCase):
    def test_pinned_original_checkout_and_actual_kext_source_phase(self):
        inputs = audit.original_inputs()
        self.assertIn(str(audit.APPLE / 'APPLE_LICENSE'), inputs)
        self.assertIn(str(audit.APPLE / 'IOKit/pci/IOPCIPrivate.h'), inputs)
        self.assertEqual(audit.target_units(), audit.UNITS)
        self.assertEqual(len(audit.UNITS), 11)
        with patch.object(audit, 'COMMIT', '0' * 40):
            with self.assertRaisesRegex(ValueError, 'Wrong Apple PCI commit'):
                audit.original_inputs()
        with patch.object(audit, 'UNITS', ('IOPCIRange.cpp',)):
            with self.assertRaisesRegex(ValueError, 'source phase changed'):
                audit.target_units()

    def test_compile_template_cannot_overwrite_original_outputs(self):
        template = dict(file='/old/source.cpp', arguments=[
            'clang', '-xc++', '/old/source.cpp', '-c', '-o', 'original.o',
            '-MD', '-MMD', '-MP', '-MF', 'original.d', '-MJ', 'original.json',
            '-MT', 'original-target', '-MQ', 'quoted-target', '-MFjoined.d',
            '-MJjoined.json', '-mcpu=cortex-a76', '-DKERNEL=1', '-I', 'real-XNU'])
        result = audit.compile_command(template, Path('/new/source.cpp'),
                                       Path('/new/include'), Path('/new/object.o'),
                                       family=Path('/separate/family'), no_apple_dart=True)
        self.assertIn('/new/source.cpp', result)
        self.assertIn('-mcpu=cortex-a76', result)
        self.assertIn('-DKERNEL=1', result)
        self.assertIn('real-XNU', result)
        self.assertIn('-DRPI5_PCI_NO_APPLE_DART=1', result)
        self.assertEqual(result[-2:], ['-o', '/new/object.o'])
        self.assertEqual(result[1:3], ['-I', '/new/include'])
        for old in ('/old/source.cpp', 'original.o', 'original.d', 'original.json',
                    'original-target', 'quoted-target', '-MFjoined.d', '-MJjoined.json',
                    '-MD', '-MMD', '-MP'):
            self.assertNotIn(old, result)
        self.assertNotIn(str(audit.ROOT / 'tools/rpi5/apple_pci_shim'), result)

    def test_pristine_real_header_screen_records_missing_dart_without_fake_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'pristine'
            report = audit.audit(output)
            self.assertFalse(report['all_source_units_compile'])
            self.assertFalse(report['adapted_copy_used'])
            self.assertFalse(report['allocator_shim_used'])
            self.assertFalse(report['fake_kernel_declarations_used'])
            self.assertIsNone(report['link'])
            self.assertEqual(report['generation']['returncode'], 0)
            results = {row['unit']: row for row in report['results']}
            self.assertEqual(set(results), set(audit.UNITS))
            self.assertNotEqual(results['IOPCIBridge.cpp']['returncode'], 0)
            self.assertTrue(any('IOKit/dart/IODARTKeys.h' in line
                                for line in results['IOPCIBridge.cpp']['errors']))
            for unit in audit.UNITS:
                if unit != 'IOPCIBridge.cpp':
                    self.assertEqual(results[unit]['returncode'], 0, unit)
            self.assertFalse((output / 'include/IOKit/dart/IODARTKeys.h').exists())
            self.assertTrue(report['consistent_original_sdk_availability_headers'])
            self.assertTrue(any(row['warning_count'] for row in results.values()))

    def test_bcm2712_full_family_compile_and_partial_link_preserve_originals(self):
        before = audit.original_inputs()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'adapted'
            report = audit.audit(output, no_apple_dart=True)
            self.assertTrue(report['all_source_units_compile'])
            self.assertTrue(report['adapted_copy_used'])
            self.assertTrue(report['original_source_unchanged'])
            self.assertEqual(len(report['adaptation']), 2)
            self.assertEqual(report['generation']['returncode'], 0)
            self.assertEqual(report['link']['returncode'], 0)
            self.assertEqual(report['link']['not_defined_in_reference_kernel'], ['___dso_handle'])
            defined = set(audit.read_command(['xcrun', 'nm', '-jU',
                                             output / 'IOPCIFamily-partial.o']).splitlines())
            for symbol in ('__ZN11IOPCIBridge10gMetaClassE', '__ZN11IOPCIDevice10gMetaClassE',
                           '__ZN17IOPCIConfigurator10gMetaClassE'):
                self.assertIn(symbol, defined)
            self.assertTrue(any('IOPCIRangeListAllocateSubRange' in name for name in defined))
            self.assertNotIn('_rpi5_apple_rp1_bar_candidates', defined)
            self.assertFalse(any('AppleVTD10gMetaClass' in name for name in defined))
            for name in ('final_kernel_link_proven', 'abi_compatibility_proven',
                         'driver_attachment_proven', 'pi_executed', 'hardware_access_enabled',
                         'sd_actions', 'serial_actions', 'reboots', 'allocator_shim_used',
                         'fake_kernel_declarations_used'):
                self.assertFalse(report[name], name)
            for name, digest in {**report['inputs_sha256'], **report['generated_sha256']}.items():
                self.assertEqual(audit.sha(Path(name)), digest, name)
            self.assertEqual(audit.sha(output / 'IOPCIFamily-partial.o'), report['link']['object_sha256'])
            for row in report['results']:
                self.assertEqual(audit.sha(output / (row['unit'] + '.o')), row['object_sha256'])
                self.assertEqual(audit.sha(Path(row['log'])), row['log_sha256'])
            family = output / 'IOPCIFamily-adapted'
            changed = {str(Path(name).relative_to(audit.APPLE)) for name, digest in before.items()
                       if audit.sha(family / Path(name).relative_to(audit.APPLE)) != digest}
            self.assertEqual(changed, {'IOPCIBridge.cpp'})
            self.assertEqual((family / 'APPLE_LICENSE').read_bytes(),
                             (audit.APPLE / 'APPLE_LICENSE').read_bytes())
            # The BCM-only exclusion must fail closed for another board profile.
            bridge = next(row for row in report['results'] if row['unit'] == 'IOPCIBridge.cpp')
            command = bridge['command'][:-2] + ['-UARM64_BOARD_CONFIG_BCM2712', '-fsyntax-only']
            result = subprocess.run(command, cwd=audit.OBJ / 'iokit/DEVELOPMENT',
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'restricted to the BCM2712 port', result.stderr)
            manifest = (output / 'manifest.json').read_bytes()
            self.assertEqual(json.loads(manifest), report)
            with self.assertRaises(FileExistsError):
                audit.audit(output, no_apple_dart=True)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
        self.assertEqual(audit.original_inputs(), before)

    def test_changed_template_and_unsafe_destination_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'rejected'
            with patch.object(audit, 'TEMPLATE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'compile template changed'):
                    audit.audit(output)
            self.assertFalse(output.exists())
        for root in (audit.APPLE, audit.OBJ, audit.SDK):
            output = root / 'do-not-create-test-screen'
            with self.assertRaisesRegex(ValueError, 'must not be inside'):
                audit.audit(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
