#!/usr/bin/env python3
"""Actual Apple case/signal objects; host evidence is not Pi execution."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_case_signal as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-ssh-case-signal-z9p6dj86'
SHA = '6536a620946ddf6cd2f497dfcec784d7e759b07a95c0ab1f9cfe04f40fe31599'


class CaseSignalProviders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA:
            raise ValueError('Frozen candidate manifest changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_actual_dependency_closure_originals_and_explicit_derivation(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items():
                self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        for relative in build.UNITS.values():
            path = build.LIBC / relative
            self.assertEqual(path.read_bytes(), subprocess.check_output(
                ['git', '-C', str(build.LIBC), 'show', 'HEAD:' + relative]))
        original = (build.LIBC / build.UNITS['strsignal']).read_text()
        derived = Path(r['derived_original_units']['string/FreeBSD/strsignal.c'])
        self.assertEqual(derived.read_text(), build.signal_derivation(original))
        self.assertFalse(r['whole_original_strsignal_unchanged'])
        self.assertTrue(r['upstream_files_unchanged'])
        self.assertEqual(build.sha(r['original_failure_receipt']),
                         r['original_failure_receipt_sha256'])

    def test_real_native_locale_tls_and_bounded_signal_regressions(self):
        executable = str(PACKAGE / 'host-case-signal')
        result = subprocess.run([executable], capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, build.EXPECTED, ''))
        for mode, diagnostic in (
            ('original-small-buffer', 'AddressSanitizer: heap-buffer-overflow'),
            ('original-int-min', "negation of -2147483648 cannot be represented in type 'int'")):
            result = subprocess.run([executable, mode], capture_output=True,
                                    text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(diagnostic, result.stderr)
        self.assertFalse(self.report['non_c_locale_files_qualified'])
        self.assertFalse(self.report['target_executed'])

    def test_exact_runtime_member_derivation_and_complete_target_ownership(self):
        r = self.report
        self.assertEqual(r['removed_legacy_members'], [build.REMOVE])
        self.assertEqual(set(r['before_members_sha256']) -
                         set(r['after_members_sha256']), {build.REMOVE})
        for name, digest in r['after_members_sha256'].items():
            data = subprocess.check_output(['xcrun', 'ar', 'p', r['runtime_archive'], name])
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        self.assertEqual(r['original_duplicate_symbols_before_owner_derivation'],
                         ['_strcasecmp', '_strncasecmp'])
        binary = r['forced_target_contract']
        self.assertEqual(build.sha(binary), r['forced_target_contract_sha256'])
        self.assertEqual(subprocess.check_output(['xcrun', 'nm', '-ju', binary], text=True), '')
        mapping = (PACKAGE / 'contract.map').read_text()
        objects = {int(number): path for number, path in
                   re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$', mapping)}
        for symbol, member in (
            ('strcasestr', 'target-strcasestr.o'),
            ('strcasecmp', 'target-strcasecmp.o'),
            ('strncasecmp', 'target-strcasecmp.o'),
            ('strsignal', 'target-strsignal.o')):
            owners = re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+_' + symbol + r'$', mapping)
            self.assertEqual(len(owners), 1, symbol)
            self.assertTrue(objects[int(owners[0])].endswith('(' + member + ')'))
        self.assertNotIn('(' + build.REMOVE + ')', mapping)

    def test_original_full_client_configuration_and_real_failed_link_delta(self):
        r = self.report
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(r['previous_missing_count'], 49)
        self.assertEqual(len(missing), 47)
        self.assertEqual(r['closed_symbols'], ['_strcasestr', '_strsignal'])
        self.assertEqual(r['newly_reachable_symbols'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        old = json.loads((build.BASE / 'manifest.json').read_text())
        before = list(next(c['command'] for c in old['commands']
                           if c['stdout'].endswith('/target-link.stdout')))
        after = list(next(c['command'] for c in r['commands']
                          if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'):
            before[before.index(flag) + 1] = after[after.index(flag) + 1]
        before[before.index(str(build.RUNTIME))] = r['runtime_archive']
        self.assertEqual(after, before + [r['target_archive']])
        self.assertTrue(r['original_openssh_config_unchanged'])
        self.assertFalse(r['target_link_complete'])
        self.assertFalse(r['accepted_runtime_modified'])
        self.assertFalse(r['network_services_executed'])


if __name__ == '__main__':
    unittest.main()
