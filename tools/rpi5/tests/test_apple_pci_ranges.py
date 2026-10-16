# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple allocator subset + RP1 policy; no physical PCI evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_apple_pci_ranges as builder

ROOT = Path(__file__).resolve().parents[3]


class ApplePCIRangesTests(unittest.TestCase):
    def test_pristine_original_unit_header_license_and_wrong_pins(self):
        snapshots = builder.inputs()
        for name, pin in builder.PINS.items():
            self.assertEqual(hashlib.sha256(snapshots[builder.APPLE/name]).hexdigest(), pin)
        with patch.object(builder, 'COMMIT', '0'*40):
            with self.assertRaisesRegex(ValueError, 'commit mismatch'): builder.inputs()
        with patch.dict(builder.PINS, {'IOPCIRange.cpp': '0'*64}):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): builder.inputs()

    def test_sanitized_original_allocator_fragmentation_and_translation_composition(self):
        builder.inputs()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            includes = ['-I', str(builder.SHIM), '-I', str(builder.APPLE),
                        '-I', str(ROOT/'loader/rpi5')]
            cpp = ['xcrun', 'clang++', '-std=c++17', '-DKERNEL=1', '-DDEVELOPMENT=0',
                   '-fno-exceptions', '-fno-rtti', '-fno-strict-aliasing',
                   '-fsanitize=address,undefined', '-Wall', '-Wextra', '-Werror', *includes]
            c = ['xcrun', 'clang', '-std=c11', '-fsanitize=address,undefined',
                 '-Wall', '-Wextra', '-Werror', *includes]
            specs = [
                (cpp+['-Wno-parentheses', '-Wno-unused-parameter'], builder.APPLE/'IOPCIRange.cpp'),
                (cpp, builder.POLICY),
                (c, ROOT/'loader/rpi5/pcie_resource_plan.c'),
                (c, Path(__file__).with_name('pcie_apple_ranges_host.c')),
            ]
            objects = []
            for flags, source in specs:
                obj = out/(source.stem+'.o')
                subprocess.run([*flags, '-c', str(source), '-o', str(obj)],
                               check=True, capture_output=True, timeout=30)
                objects.append(str(obj))
            program = out/'ranges'
            subprocess.run(['xcrun', 'clang++', '-fsanitize=address,undefined',
                            *objects, '-o', str(program)], check=True, timeout=30)
            result = subprocess.run([str(program)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout,
                b'APPLE_RANGE_HOST_PASS CASES=4096 SUCCESS=4081 EXHAUSTED=15 NO_MMIO=1\n')

    def test_real_a76_composed_object_records_all_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/'build'
            report = builder.build(out)
            self.assertTrue(report['original_allocator_linked'])
            self.assertTrue(report['original_source_unchanged'])
            self.assertTrue(report['original_range_header_unchanged'])
            self.assertTrue(report['kernel_classes_omitted'])
            self.assertTrue(report['heap_and_unexpected_logger_paths_trap'])
            self.assertEqual(report['source_commit'], builder.COMMIT)
            self.assertEqual(report['max_upstream_allocate_calls'], 11)
            for group in ('source_inputs_sha256', 'compiler_headers_sha256'):
                self.assertTrue(report[group])
                for name, pin in report[group].items():
                    self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), pin)
            for name, pin in report['outputs_sha256'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), pin)
            self.assertEqual(subprocess.check_output(
                ['xcrun', 'llvm-nm', '--undefined-only', str(out/'apple-rp1-ranges.o')],
                text=True, timeout=10).strip(), '')
            for name in ('bar_assignment_proven', 'entire_iopcifamily_kernel_compatibility_proven',
                         'pi_executed', 'hardware_access_enabled', 'nic_ready',
                         'sd_actions', 'serial_actions', 'reboots',
                         'unused_decode_padding_allocatable'):
                self.assertFalse(report[name], name)
            manifest = (out/'manifest.json').read_bytes()
            self.assertEqual(json.loads(manifest), report)
            with self.assertRaises(FileExistsError): builder.build(out)
            self.assertEqual((out/'manifest.json').read_bytes(), manifest)


if __name__ == '__main__':
    unittest.main()
