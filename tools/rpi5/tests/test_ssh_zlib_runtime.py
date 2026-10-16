#!/usr/bin/env python3
"""Original release, actual source closure and SDK-header stream execution."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_ssh_zlib_runtime as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/ssh-zlib-runtime-jl5uvvmb'
MANIFEST_SHA = '01e691fec55406c122053f48a398f37cd625ae95b6c87b73890acba21d3de2b5'


class ZlibRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != MANIFEST_SHA:
            raise ValueError('Frozen zlib receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_release_and_exact_consumed_source_closure(self):
        r = self.report
        self.assertEqual(build.sha(build.INPUT / 'zlib-1.3.2.tar.gz'), build.ARCHIVE_SHA)
        self.assertEqual(r['requested_translation_units'], build.original_units())
        self.assertEqual(len(r['requested_translation_units']), 15)
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items():
                self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        incomplete = dict(r, headers_sha256=dict(r['headers_sha256']))
        incomplete['headers_sha256'].pop(next(iter(incomplete['headers_sha256'])))
        with self.assertRaises(ValueError):
            actual_dependencies(incomplete)
        sdk = Path(next(c['command'][c['command'].index('-isysroot') + 1]
            for c in r['commands'] if c['stdout'].endswith('/sdk-client-compile.stdout')))
        consumed = r['dependency_records']['sdk-client']['consumed_sha256']
        self.assertIn(str((sdk / 'usr/include/zlib.h').resolve()), consumed)
        self.assertNotIn(str(build.SOURCE / 'zlib.h'), consumed)

    def test_original_upstream_and_sdk_client_execute(self):
        with tempfile.TemporaryDirectory(prefix='zlib-example-', dir=build.ROOT / 'build/rpi5') as directory:
            run = subprocess.run([str(PACKAGE / 'original-example'), str(Path(directory) / 'example.gz')],
                capture_output=True, text=True, timeout=15)
            self.assertEqual((run.returncode, run.stdout, run.stderr),
                (0, self.report['original_example_stdout'], ''))
        run = subprocess.run([str(PACKAGE / 'sdk-client')], capture_output=True, text=True, timeout=15)
        self.assertEqual((run.returncode, run.stdout, run.stderr), (0, build.EXPECTED, ''))
        dylibs = subprocess.check_output(['xcrun', 'otool', '-L', str(PACKAGE / 'sdk-client')], text=True)
        self.assertNotRegex(dylibs, r'/libz\.')

    def test_actual_full_client_compression_delta(self):
        r = self.report
        command = next(c for c in r['commands'] if c['stdout'].endswith('/target-link.stdout'))
        stderr = Path(command['stderr']).read_text()
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', stderr, re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(len(missing), 96)
        self.assertEqual(r['closed_symbols'], sorted(build.CLOSED))
        self.assertEqual(r['newly_reachable_dependencies'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        self.assertEqual(command['command'][-1], r['target_archive'])
        self.assertTrue(r['upstream_sources_unchanged'])
        self.assertTrue(r['original_openssh_config_unchanged'])
        self.assertFalse(r['target_link_complete'])
        self.assertFalse(r['target_executed'])
        self.assertFalse(r['provider_stubs'])


if __name__ == '__main__':
    unittest.main()
