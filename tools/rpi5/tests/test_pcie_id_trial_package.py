# SPDX-License-Identifier: BSD-2-Clause
"""Read-only admission mutations; never rewrite the pinned package."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_pcie_id_trial_package as checker


class PCIeIDPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ.get('RPI5_PCIE_ID_PACKAGE',
            str(checker.builder.ROOT / 'build/rpi5/pcie-id-trial-wpo7wy6_'))).resolve()
        cls.manifest = cls.package / 'manifest.json'
        cls.original = json.loads(cls.manifest.read_text())
        cls.passed = checker.inspect(cls.package)  # Actual ASan/UBSan and complete live dependency audit.
        cls.inputs = checker.builder.inputs()

    def reject(self, mutate, expected):
        record = copy.deepcopy(self.original)
        mutate(record)
        read = Path.read_text
        def injected(path, *args, **kwargs):
            return json.dumps(record) if path == self.manifest else read(path, *args, **kwargs)
        # Cache expensive immutable parent receipts/native execution after real setUp validation.
        # The mutated manifest still passes through all actual checker comparisons and ELF parsing.
        with patch.object(Path, 'read_text', injected), \
             patch.object(checker.builder, 'inputs', return_value=self.inputs), \
             patch.object(checker.builder.handoff_contract, 'audit',
                 return_value=self.passed['native_handoff_contract']):
            with self.assertRaisesRegex(ValueError, expected):
                checker.inspect(self.package)

    def test_complete_actual_pair(self):
        self.assertTrue(self.passed['preflight_pass'])
        self.assertEqual(len(self.passed['boot_markers']), 4)
        self.assertFalse(self.passed['serial_input_allowed'])
        self.assertTrue(self.passed['native_handoff_contract']['missing_descriptor_rejected'])

    def test_omitted_compiler_header_rejected(self):
        self.reject(lambda m: m['headers_sha256'].pop(next(iter(m['headers_sha256']))),
            'complete_header_closure')

    def test_omitted_generated_pin_rejected(self):
        self.reject(lambda m: m['generated_sha256'].pop(str(self.package / 'probe_main.o')),
            'complete_generated_closure')

    def test_boot_admission_reordering_rejected(self):
        self.reject(lambda m: m['boot_markers'].reverse(), 'ordered_boot_markers')

    def test_false_watchdog_bound_rejected(self):
        self.reject(lambda m: m['watchdog'].update(transfer_to_bootsys_bound_seconds=3600),
            'exact_watchdog')

    def test_wrong_kernel_descriptor_type_rejected(self):
        self.reject(lambda m: m['kernel_handoff_binding'].update(memory_type=2),
            'actual_kernel_fdt_binding')


if __name__ == '__main__':
    unittest.main()
