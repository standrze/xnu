# SPDX-License-Identifier: BSD-2-Clause
"""Declaration-only loader and actual kernel memory-type decode; no board I/O."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_device_handoff as builder
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree, _encode_fdt, _cells


class PCIeDeviceHandoffTests(unittest.TestCase):
    def test_sanitized_raw_fdt_exact_expansion_and_real_kernel_decode(self):
        root = _synthetic_tree()
        wrong = copy.deepcopy(root)
        wrong['children'][1]['children'][0]['properties']['num-lanes'] = _cells(1)
        cases = [(_encode_fdt(root), 'accept'), (_encode_fdt(wrong), 'reject'), (b'not fdt', 'reject')]
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); program = work / 'handoff'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(builder.CORE.parent),
                str(Path(__file__).with_name('pcie_device_handoff_host.c')),
                *(str(builder.CORE.with_name(name + '.c')) for name in
                  ('pcie_device_handoff', 'pcie_fdt', 'fdt', 'fdt_reg', 'memory_type',
                   'board_tree', 'cpu_tree', 'serial_tree', 'apple_dt')),
                '-o', str(program)], check=True, capture_output=True, timeout=60)
            for i, (data, expected) in enumerate(cases):
                fixture = work / (str(i) + '.dtb'); fixture.write_bytes(data)
                result = subprocess.run([str(program), str(fixture), expected], capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, b'PCIE_DEVICE_HANDOFF_PASS EXACT_PAGES=5 APPLE_TREE=1 KERNEL_DECODE=1 NO_MMIO=1\n'
                                 if expected == 'accept' else b'PCIE_DEVICE_HANDOFF_REJECT NO_MMIO=1\n')

    def test_actual_loader_link_opt_out_equivalence_payload_and_input_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'build'
            report = builder.build(output)
            self.assertTrue(report['baseline_object_replay_identical'])
            self.assertTrue(report['disabled_patch_boot_binary_identical'])
            self.assertTrue(report['accepted_kernel_and_root_reused'])
            self.assertEqual(report['added_device_pages'], 5)
            self.assertEqual(report['embedded_kernel_sha256'],
                             '674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad')
            self.assertEqual(report['embedded_root_sha256'], builder.accepted.INIT_SHA)
            self.assertEqual(report['elf_audit']['entry'], 0x9000000)
            self.assertEqual(builder.audit.sha(output / 'handoff.bin'), report['image_sha256'])
            for key in ('legacy_installer_schema_compatible', 'device_typing_is_hardware_permission',
                        'pcie_mmio_enabled', 'phy_driver_registered', 'pcie_reset_writes', 'dma_authorized',
                        'irq_enabled', 'power_clock_admission_proven', 'reset_destination_proven',
                        'installed', 'pi_executed', 'sd_actions', 'serial_actions', 'reboots'):
                self.assertFalse(report[key], key)
            for name, digest in {**report['inputs_sha256'], **report['generated_sha256']}.items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            for row in report['commands']:
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(row['warning_count'], 0)
            self.assertGreater(report['stack_budgets']['device_handoff']['minimum_remaining_bytes'], 512)
            with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
                builder.accepted.inspect(output)
            manifest = (output / 'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError): builder.build(output)
            self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
            command = next(row['command'] for row in report['commands'] if row['log'].endswith('/main.log'))
            source = output / 'probe_main.c'
            self.assertIn(str(source.resolve()), command)
            for switch in ('RPI5_GATE4_STORAGE', 'RPI5_GATE5_PCIE_TOPOLOGY', 'RPI5_SERIAL_TERMINAL'):
                bad = [arg for arg in command[:-2] if arg != '-c']
                bad += ['-U' + switch, '-D' + switch + '=' + ('1' if switch == 'RPI5_GATE4_STORAGE' else '0'),
                        '-fsyntax-only']
                result = subprocess.run(bad, cwd=builder.ROOT, capture_output=True, timeout=60)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'separate topology/terminal transfer profile', result.stderr)

    def test_stack_missing_duplicate_and_over_budget_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = builder.build(Path(temporary) / 'build')
        frames = report['stack_frames']
        required = 'loader/rpi5/pcie_device_handoff.c:rpi5_pcie_device_handoff'
        selected = next(row for row in frames if row['location'].startswith('loader/rpi5/pcie_device_handoff.c:'))
        bad = [row for row in frames if row != selected]
        with self.assertRaisesRegex(ValueError, 'Missing'): builder.device_stack(bad)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): builder.device_stack(frames + [selected])
        bad = copy.deepcopy(frames)
        next(row for row in bad if row['location'].split(':')[0] + ':' + row['location'].split(':')[-1] == required)['bytes'] = 16384
        with self.assertRaisesRegex(ValueError, 'exhausts'): builder.device_stack(bad)

    def test_accepted_drift_and_unsafe_output_refused(self):
        with patch.object(builder, 'BASE_MANIFEST_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'loader changed'): builder.inputs()
        for root in (builder.BASE, builder.ROOT / 'loader', builder.ROOT / 'iokit', builder.audit.OBJ):
            output = root / 'do-not-create-handoff-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
