# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import build_root96_fdt_package as builder
from tools.rpi5 import check_root96_fdt_package as checker
from tools.rpi5.tests import test_firmware_fdt_handoff as original


class Root96FDTTests(unittest.TestCase):
    PACKAGE = builder.ROOT / 'build/rpi5/root96-fdt-euspad_2'

    def test_exact_failed_composition_is_rejected(self):
        record = json.loads((self.PACKAGE / 'manifest.json').read_text())
        with self.assertRaisesRegex(ValueError, 'lacks linked retained-FDT'):
            builder.handoff_contract(builder.FAILED, Path(record['kernel']))

    def test_corrected_loader_exact_kernel_and_root_are_compatible(self):
        result = checker.inspect(self.PACKAGE)
        self.assertTrue(result['preflight_pass'])
        self.assertTrue(all(result['corrected_checks'].values()))
        self.assertEqual(result['kernel_sha256'], builder.failed.KERNEL_SHA)
        self.assertEqual(result['init_sha256'], builder.failed.ROOT_SHA)
        self.assertNotEqual(result['image_sha256'], builder.failed.PACKAGE_SHA)
        self.assertFalse(result['pi_executed'])

    def test_actual_descriptor_serialization_retention_and_seed_transaction(self):
        # Exercise the actual retained encoder/resolver/decoder with explicit
        # synthetic RAM/FDT, not a string-only compatibility assertion.
        case = original.FirmwareFDTHandoffTests()
        case.output = builder.LOADER
        case.test_native_serialized_descriptor_retention_private_seed_redaction_and_pcie_decode()

    def test_missing_generated_and_header_maps_are_rejected(self):
        manifest = self.PACKAGE / 'manifest.json'
        original = Path.read_text
        for field in ('generated_sha256', 'headers_sha256'):
            mutated = json.loads(manifest.read_text())
            mutated[field] = {}
            def read(path, *args, **kwargs):
                return json.dumps(mutated) if path == manifest else original(path, *args, **kwargs)
            with self.subTest(field=field), patch.object(Path, 'read_text', read):
                with self.assertRaisesRegex(ValueError, 'complete_.*closure'):
                    checker.inspect(self.PACKAGE)


if __name__ == '__main__':
    unittest.main()
