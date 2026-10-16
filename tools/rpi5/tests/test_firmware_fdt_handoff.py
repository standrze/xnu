# SPDX-License-Identifier: BSD-2-Clause
"""Real retained-FDT loader/kernel components; no physical hardware operations."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_firmware_fdt_handoff as builder
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree, _encode_fdt, _node
from tools.rpi5.tests.test_handoff import image


class FirmwareFDTHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'build'
        cls.report = builder.build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_native_serialized_descriptor_retention_private_seed_redaction_and_pcie_decode(self):
        root = _synthetic_tree()
        root['children'].append(_node('chosen', {'rng-seed': bytes(range(64)),
            'kaslr-seed': b'K' * 8, 'random-seed': b'R' * 256}))
        minimal = copy.deepcopy(root)
        minimal['children'][-1]['properties'] = {'rng-seed': b'Q' * 64}
        missing = copy.deepcopy(root)
        del missing['children'][-1]['properties']['rng-seed']
        short = copy.deepcopy(root)
        short['children'][-1]['properties']['rng-seed'] = b'Q' * 63
        duplicate = copy.deepcopy(root)
        duplicate['children'].append(copy.deepcopy(duplicate['children'][-1]))
        cases = [(_encode_fdt(root), 'accept', 3), (_encode_fdt(minimal), 'accept', 1),
                 (_encode_fdt(missing), 'reject', 0), (_encode_fdt(short), 'reject', 0),
                 (_encode_fdt(duplicate), 'reject', 0), (_encode_fdt(root)[:-1], 'reject', 0),
                 (b'not an FDT', 'reject', 0)]
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); program = work / 'native'
            cores = ('firmware_fdt_tree', 'fdt_sanitize', 'pcie_fdt', 'fdt', 'fdt_reg', 'board_tree',
                'memory_type', 'cpu_tree', 'serial_tree', 'apple_dt', 'seed_tree', 'boot_seed',
                'tree_handoff', 'handoff', 'bootstrap', 'boot_args', 'ranges', 'macho', 'reservations')
            # Execute the real reservation resolver, not a caller-made free map.
            sources = [builder.ROOT / ('loader/rpi5/' + name + '.c') for name in cores]
            compiled = subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-DRPI5_FIRMWARE_FDT_HANDOFF=1', '-fsanitize=address,undefined',
                '-I', str(builder.ROOT / 'loader/rpi5'),
                str(Path(__file__).with_name('firmware_fdt_host.c')),
                str(self.output / 'firmware_seed_tree.c'), *map(str, sources), '-o', str(program)],
                capture_output=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            macho = work / 'kernel'; macho.write_bytes(image())
            for i, (data, mode, seeds) in enumerate(cases):
                fixture = work / (str(i) + '.dtb'); fixture.write_bytes(data)
                result = subprocess.run([str(program), str(fixture), str(macho), mode],
                    capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout,
                    f'FIRMWARE_FDT_PASS SEEDS={seeds} RETAINED=1 APPLE_TREE=1 PCIE_DECODE=1 NO_MMIO=1\n'.encode()
                    if mode == 'accept' else b'FIRMWARE_FDT_REJECT ATOMIC=1 NO_MMIO=1\n')

    def test_real_build_opt_out_equivalence_and_unchanged_payload(self):
        r = self.report
        for key in ('disabled_patch_boot_binary_identical', 'accepted_kernel_and_root_reused_in_loader',
                    'loader_exports_descriptor_only', 'actual_normal_physmap_view_implemented',
                    'actual_private_osdata_copy_implemented', 'known_boot_seed_values_erased_in_copy',
                    'copy_consumed_by_pcie_owner'):
            self.assertTrue(r[key], key)
        for key in ('original_firmware_source_changed', 'final_kernel_link_proven',
                    'provider_registration_implemented', 'installed', 'pi_executed',
                    'power_clock_ownership_proven', 'hardware_recovery_proven', 'pcie_mmio_enabled',
                    'ethernet_proven', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key], key)
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        self.assertGreater(r['stack_budgets']['firmware_fdt']['minimum_remaining_bytes'], 512)
        self.assertEqual(r['embedded_kernel_sha256'], '674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad')
        self.assertEqual(r['image_sha256'], builder.audit.sha(self.output / 'firmware-fdt.bin'))
        for row in r['commands']:
            self.assertEqual(row['returncode'], 0)
            self.assertEqual(row['warning_count'], int(row['log'].endswith(('/arm_init.c-compile.log', '/baseline-arm-compile.log'))))
        self.assertEqual(r['kernel_link']['not_defined_in_reference_kernel'],
            ['___dso_handle', 'section$end$__TEXT$__thread_starts', 'section$start$__TEXT$__thread_starts'])
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError): builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            builder.device.accepted.inspect(self.output)

    def test_wrong_profiles_rejected_by_actual_compiler(self):
        for row in self.report['kernel_results'][1:3]:
            command = [arg for arg in row['command'][:-2] if arg != '-c']
            result = subprocess.run(command + ['-URPI5_FIRMWARE_FDT_HANDOFF', '-fsyntax-only'],
                cwd=builder.audit.OBJ / 'iokit/DEVELOPMENT', capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'separate', result.stderr)
        command = next(row['command'] for row in self.report['commands'] if row['log'].endswith('/loader-main.log'))
        bad = [arg for arg in command[:-2] if arg != '-c'] + ['-URPI5_PCIE_DEVICE_HANDOFF',
            '-DRPI5_PCIE_DEVICE_HANDOFF=0', '-fsyntax-only']
        result = subprocess.run(bad, cwd=builder.ROOT, capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Device/terminal transfer profile', result.stderr)

    def test_dependency_drift_and_unsafe_output_refused(self):
        with patch.object(builder, 'LOADER_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'dependency receipt changed'): builder.inputs()
        for root in (builder.ROOT / 'loader', builder.ROOT / 'osfmk', builder.LOADER,
                     builder.KERNEL, builder.audit.OBJ, builder.device.BASE):
            output = root / 'do-not-create-fdt-test'
            with self.assertRaisesRegex(ValueError, 'must not be inside'): builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
