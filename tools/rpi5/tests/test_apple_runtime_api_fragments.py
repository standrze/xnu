#!/usr/bin/env python3
"""Exact selected Apple reallocf/crash bodies, not whole-library qualification."""
import json
from pathlib import Path
import re
import subprocess
import unittest

from tools.rpi5 import build_apple_runtime_api_fragments as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-runtime-api-fragments-bg8jq8u2'
MANIFEST_SHA = '6c858250877f14585768a8d3beb77b44a0c321c68227fc8cfe3934df88193ade'


class SelectedAppleAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != MANIFEST_SHA:
            raise ValueError('Selected API receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_exact_original_fragments_and_consumed_headers(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items():
                self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertEqual(set(r['dependency_records']), {
            'target-reallocf', 'target-crash', 'native-reallocf', 'native-crash', 'native-caller'})
        for name, text in build.fragments().items():
            self.assertEqual(Path(r['generated_fragment_files'][name]).read_text(), text)
        for repo, commit in build.COMMITS.items():
            self.assertEqual(subprocess.check_output(
                ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(), commit)
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):
            actual_dependencies(bad)
        with self.assertRaises(ValueError):
            build.between('ambiguous ambiguous end', 'ambiguous', 'end')
        with self.assertRaises(ValueError):
            build.between('start only', 'start', 'missing')
        self.assertTrue(r['selected_function_bodies_unchanged'])
        self.assertTrue(r['original_license_headers_preserved'])
        self.assertFalse(r['whole_original_translation_units_compiled'])

    def test_original_native_errno_callback_and_caller_trap(self):
        result = subprocess.run([str(PACKAGE / 'host-contract')],
            capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        self.assertTrue(self.report['original_caller_trap_retained'])
        self.assertTrue(self.report['original_crash_callback_retained'])
        self.assertTrue(self.report['host_allocator_calls_are_explicit_doubles'])

    def test_actual_target_archive_and_full_client_delta(self):
        r = self.report
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', r['target_archive']], text=True)
        for name in ('_reallocf', '__os_crash', '__os_crash_callback'):
            self.assertRegex(symbols, r'(?m)^[0-9a-f]+ [TBDS] ' + re.escape(name) + r'$')
        disassembly = (PACKAGE / 'disassembly.stdout').read_text()
        for name in ('_realloc', '_free', '___error'):
            self.assertIn('ARM64_RELOC_BRANCH26\t' + name, disassembly)
        self.assertIn('__os_crash_callback', disassembly)
        self.assertRegex(disassembly, r'\bbr\s+x[0-9]+')
        command = next(c for c in r['commands'] if c['stdout'].endswith('/target-link.stdout'))
        stderr = Path(command['stderr']).read_text()
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', stderr, re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(len(missing), 52)
        self.assertEqual(r['closed_symbols'], ['__os_crash', '_reallocf'])
        self.assertEqual(r['newly_reachable_dependencies'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        self.assertFalse(r['target_link_complete'])
        self.assertFalse(r['target_executed'])
        self.assertFalse(r['full_libmalloc_or_logging_qualified'])
        self.assertTrue(r['original_openssh_config_unchanged'])
        self.assertFalse(r['accepted_runtime_modified'])


if __name__ == '__main__':
    unittest.main()
