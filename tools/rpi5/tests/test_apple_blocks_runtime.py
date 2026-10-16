#!/usr/bin/env python3
"""Whole original Blocks runtime; no target dispatch_once or Pi execution claim."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_blocks_runtime as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-blocks-runtime-ga1_x5sg'
SHA = '447d6841cc058fd09ad8ef39ed9e338db364c88850ad207b7df4e56e709f49f5'


class AppleBlocksRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA:
            raise ValueError('Original Blocks receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_source_release_headers_and_explicit_scope(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items():
                self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)
        self.assertEqual(r['whole_original_translation_units_compiled'], list(build.UNITS))
        self.assertTrue(r['release_file_bytes_verified'])
        self.assertFalse(r['original_source_modified'])
        self.assertFalse(r['objective_c_enabled'])
        self.assertFalse(r['accepted_runtime_modified'])
        self.assertFalse(r['target_executed'])

    def test_actual_original_native_blocks_not_system_provider(self):
        result = subprocess.run([str(PACKAGE / 'host-blocks')],
            capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        text = (PACKAGE / 'host.map').read_text()
        for symbol in ('__Block_copy', '__Block_release', '__Block_object_assign', '__Block_object_dispose'):
            self.assertRegex(text, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*2\] ' + symbol + r'$')
        for symbol in ('__NSConcreteStackBlock', '__NSConcreteGlobalBlock', '__NSConcreteMallocBlock'):
            self.assertRegex(text, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*3\] ' + symbol + r'$')
        self.assertTrue(self.report['native_blocks_runtime_from_original_objects'])

    def test_actual_target_exports_and_honest_once_failure(self):
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.report['target_archive']], text=True)
        for name in ('__Block_copy', '__Block_release', '__Block_object_assign', '__Block_object_dispose',
                '__NSConcreteStackBlock', '__NSConcreteGlobalBlock', '__NSConcreteMallocBlock'):
            self.assertRegex(symbols, r'(?m)^[0-9a-f]+ [TS] ' + re.escape(name) + r'$')
        self.assertNotIn('_dispatch_once', symbols)
        self.assertEqual(self.report['once_compile_returncode'], 1)
        self.assertIn('error:', (PACKAGE / 'original-once-inventory.stderr').read_text())
        self.assertFalse(self.report['dispatch_once_provider_qualified'])
        self.assertFalse(self.report['exclavekit_noop_used'])


if __name__ == '__main__':
    unittest.main()
