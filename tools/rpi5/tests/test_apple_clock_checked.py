# SPDX-License-Identifier: BSD-2-Clause
"""Validate actual clock artifacts, not a replacement Python clock model."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_clock_checked as builder

PACKAGE = builder.ROOT / 'build/rpi5/apple-clock-checked-acrq3vpm'
MANIFEST_SHA = 'a2db7650517f1a30ba7374f9737ed18965c92fd4ec2126596e85febe193b7a52'


class AppleClockCheckedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = PACKAGE / 'manifest.json'
        if builder.sha(path) != MANIFEST_SHA:
            raise AssertionError('Exact checked clock package required')
        cls.report = json.loads(path.read_text())

    def test_exact_inputs_outputs_consumed_headers_and_original_helpers(self):
        report = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in report[key].items():
                self.assertEqual(builder.sha(name), digest, name)
        for record in report['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'], record['consumed_sha256'])
        inventory = json.loads((builder.BASE / 'manifest.json').read_text())
        self.assertEqual(report['original_mach_helpers'], inventory['objects'][1:])
        self.assertEqual(len(report['original_mach_helpers']), 3)
        self.assertFalse(report['target_executed'])
        self.assertFalse(report['accepted_runtime_modified'])

    def test_exact_derived_body_original_unchanged_and_native_negative_oracles(self):
        report = self.report
        original = Path(report['original_clock_source'])
        upstream = subprocess.check_output(['git', '-C', str(builder.inventory.base.LIBC),
                                            'show', 'HEAD:gen/clock_gettime.c'])
        self.assertEqual(original.read_bytes(), upstream)
        self.assertEqual(Path(report['derived_clock_source']).read_text(), builder.derive(original.read_text()))
        for label in ('original', 'derived'):
            result = subprocess.run([str(PACKAGE / ('host-' + label)), label],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'APPLE_CLOCK ' + label.upper() + ' PASS\n')
            self.assertEqual(result.stderr, '')
        self.assertTrue(report['native_original_fallback_false_success_reproduced'])
        self.assertTrue(report['native_fallback_first_second_and_persistent_errors_propagated'])
        self.assertEqual(report['native_rational_scale_cases'], 36936)

    def test_full_original_client_link_delta_and_no_boundary_doubles(self):
        report = self.report
        prior = json.loads((builder.inventory.predecessor.PREDECESSOR / 'manifest.json').read_text())
        error = (PACKAGE / 'target-link.stderr').read_text()
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', error, re.M)))
        duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", error)))
        self.assertEqual(missing, report['target_missing_symbols'])
        self.assertEqual(len(missing), 46)
        self.assertEqual(set(prior['target_missing_symbols']) - set(missing), {'_clock_gettime'})
        self.assertEqual(set(missing) - set(prior['target_missing_symbols']), set())
        self.assertEqual(duplicates, [])
        self.assertTrue(report['original_openssh_config_unchanged'])
        actual = next(c['command'] for c in report['commands'] if c['label'] == 'target-link')
        expected = list(next(c['command'] for c in prior['commands'] if c['stdout'].endswith('/target-link.stdout')))
        expected[expected.index('-o') + 1] = str(PACKAGE / 'NOT_RUN_ssh')
        expected[expected.index('-map') + 1] = str(PACKAGE / 'target.map')
        self.assertEqual(actual, expected + [report['target_archive']])
        symbols = (PACKAGE / 'symbols.stdout').read_text()
        self.assertNotIn('fixture_', symbols)
        self.assertNotIn('___udivti3', symbols)
        members = subprocess.check_output(['xcrun', 'ar', 't', report['target_archive']], text=True).splitlines()
        self.assertEqual(members, ['__.SYMDEF SORTED', 'target-clock.o', 'mach_boottime.o',
                                   'mach_approximate_time.o', 'thread-selfusage.o'])
        self.assertFalse(report['target_link_complete'])

    def test_forced_target_read_contract_and_preserved_setter_failure(self):
        from tools.rpi5 import prepare_pid1
        cases = (
            ('apple-clock-static-contract-9g46utl5',
             'a2c7ee6b6510e86b8447fd7c4fc41a155ac0939dc8032f89aa10f56e16364209'),
            ('apple-clock-read-contract-mrnnxc8f',
             'e5ef9437d8eb3aa615a17c8f7b972c3dc7e7f44d64ea0f82c0aaab0c348ee64e'))
        reports = []
        for name, digest in cases:
            path = builder.ROOT / 'build/rpi5' / name / 'manifest.json'
            self.assertEqual(builder.sha(path), digest)
            report = json.loads(path.read_text())
            for key in ('source_inputs_sha256', 'generated_sha256'):
                for source, expected in report[key].items():
                    self.assertEqual(builder.sha(source), expected, source)
            self.assertFalse(report['target_executed'])
            reports.append(report)
        failed, passed = reports
        self.assertFalse(failed['linked'])
        self.assertEqual(failed['missing_symbols'], ['_settimeofday'])
        self.assertEqual(failed['duplicate_symbols'], [])
        self.assertFalse(passed['setter_qualified'])
        target = Path(passed['target'])
        self.assertEqual(prepare_pid1.inspect(target.read_bytes()), passed['static_inspection'])
        undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(target)], text=True)
        self.assertEqual(undefined, '')
        mapping = target.parent / 'contract.map'
        text = mapping.read_text()
        objects = {int(n): path for n, path in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$', text)}
        for symbol, owner in passed['live_symbol_owners'].items():
            numbers = re.findall(r'(?m)^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+' + re.escape(symbol) + '$', text)
            self.assertEqual(len(numbers), 1, symbol)
            self.assertEqual(objects[int(numbers[0])], owner)
        self.assertEqual(len(passed['live_symbol_owners']), 13)
        self.assertNotRegex(text, r'(fixture_|__asan|__ubsan|___udivti3)')


if __name__ == '__main__':
    unittest.main()
