#!/usr/bin/env python3
"""Original rejection sampler, concrete API delegation and full-client delta."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_kernel_entropy_word_api as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/kernel-entropy-word-z34ff8bs'
SHA = 'e9467381132ecd13d800696361422234c55ee0156d59e184a213a220940eb2c6'


class RandomWordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA:
            raise ValueError('Frozen API receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_original_inputs_and_consumed_caller_headers(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items():
                self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertIn('native-caller', r['dependency_records'])
        for name in ('stdio.h', 'string.h', 'stdlib.h', 'stdint.h'):
            self.assertTrue(any(p.endswith('/' + name)
                for p in r['dependency_records']['native-caller']['consumed_sha256']))
        incomplete = dict(r, headers_sha256=dict(r['headers_sha256']))
        incomplete['headers_sha256'].pop(next(iter(incomplete['headers_sha256'])))
        with self.assertRaises(ValueError):
            actual_dependencies(incomplete)

    def test_actual_sampler_boundaries_and_residue_groups(self):
        result = subprocess.run([str(PACKAGE / 'synthetic-source-host')],
            capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        self.assertTrue(self.report['native_source_is_synthetic'])
        self.assertFalse(self.report['entropy_qualified'])

    def test_actual_a76_delegation_and_original_full_client_delta(self):
        text = (PACKAGE / 'disassembly.stdout').read_text()
        self.assertRegex(text, r'mov\s+w1, #0x4')
        self.assertIn('ARM64_RELOC_BRANCH26\t_arc4random_buf', text)
        self.assertIn('ARM64_RELOC_BRANCH26\t_arc4random\n', text)
        self.assertIn('udiv', text)
        self.assertIn('b.lo', text)
        for object_, expected in (('target-word.o', '_arc4random_buf'), ('target-uniform.o', '_arc4random')):
            undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(PACKAGE / object_)], text=True)
            self.assertEqual(undefined, expected + '\n')
            symbols = subprocess.check_output(['xcrun', 'nm', '-g', str(PACKAGE / object_)], text=True)
            self.assertNotRegex(symbols, r'(?m)^[0-9a-f]+ [BDCS] ')
        command = next(c for c in self.report['commands'] if c['stdout'].endswith('/target-link.stdout'))
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', Path(command['stderr']).read_text(), re.M)))
        self.assertEqual(missing, self.report['target_missing_symbols'])
        self.assertEqual(len(missing), 100)
        self.assertEqual(self.report['closed_symbols'], ['_arc4random', '_arc4random_uniform'])
        self.assertEqual(self.report['newly_reachable_dependencies'], [])
        self.assertEqual(self.report['target_duplicate_symbols'], [])
        self.assertFalse(self.report['target_link_complete'])
        self.assertFalse(self.report['target_executed'])
        self.assertFalse(self.report['user_space_generator'])
        self.assertFalse(self.report['retained_random_state'])


if __name__ == '__main__':
    unittest.main()
