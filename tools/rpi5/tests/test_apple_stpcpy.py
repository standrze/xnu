#!/usr/bin/env python3
"""Whole original Apple stpcpy and real full-client provider delta."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_stpcpy as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-stpcpy-i77u3elg'
SHA = '2af08054a8d368beb4fe0dceb53e89c0c9b0dcd376be0bb132ab7875bcba9381'


class AppleStpcpy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA: raise ValueError('stpcpy receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_original_whole_source_and_actual_header_closure(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items(): self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertEqual(set(r['dependency_records']), {'target-stpcpy', 'native-stpcpy', 'native-caller'})
        self.assertEqual(subprocess.check_output(['git', '-C', str(build.LIBC), 'show', 'HEAD:string/stpcpy.c']),
            build.SOURCE.read_bytes())
        self.assertTrue(r['original_source_unchanged']); self.assertTrue(r['whole_original_translation_unit_compiled'])
        for command in r['commands']:
            if '-MF' in command['command']: self.assertIn('-D_FORTIFY_SOURCE=0', command['command'])
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)

    def test_original_native_alignment_lengths_and_guard_bytes(self):
        result = subprocess.run([str(PACKAGE / 'host-stpcpy')], capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))

    def test_actual_target_leaf_calls_and_unchanged_client_composition(self):
        r = self.report
        names = subprocess.check_output(['xcrun', 'nm', '-g', r['target_archive']], text=True)
        self.assertRegex(names, r'(?m)^[0-9a-f]+ T _stpcpy$')
        undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(PACKAGE / 'target-stpcpy.o')], text=True)
        self.assertEqual(set(undefined.splitlines()), {'_strlen', '_memcpy'})
        disassembly = (PACKAGE / 'disassembly.stdout').read_text()
        for name in ('_strlen', '_memcpy'): self.assertIn('ARM64_RELOC_BRANCH26\t' + name, disassembly)
        self.assertNotIn('__stpcpy_chk', disassembly)
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols']); self.assertEqual(len(missing), 55)
        self.assertEqual(r['closed_symbols'], ['_stpcpy']); self.assertEqual(r['newly_reachable_symbols'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        base = json.loads((build.BASE / 'manifest.json').read_text())
        old = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new = list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'): old[old.index(flag) + 1] = new[new.index(flag) + 1]
        self.assertEqual(new, old + [r['target_archive']])
        self.assertTrue(r['original_openssh_config_unchanged'])
        self.assertFalse(r['target_link_complete']); self.assertFalse(r['target_executed'])
        self.assertFalse(r['accepted_runtime_modified'])


if __name__ == '__main__': unittest.main()
