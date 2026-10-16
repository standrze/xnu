#!/usr/bin/env python3
"""Original checked copy bounds, padding, post-copy overlap and target calls."""
import json
from pathlib import Path
import re
import signal
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_strncpy_chk as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-ssh-strncpy-chk-uhooi_u9'
SHA = 'cb674efb3ebad4d28e68f519557f199bd748d57c599ead438b616dcdcc29acf9'


class StrncpyChecked(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA: raise ValueError('Frozen checked-copy receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_whole_original_sources_and_actual_dependency_membership(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items(): self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertEqual(set(r['dependency_records']),
            {'target-strncpy_chk', 'target-stpncpy', 'native-strncpy_chk', 'native-stpncpy', 'native-caller'})
        for record in r['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'], record['consumed_sha256'])
        for path in build.SOURCES.values():
            self.assertEqual(path.read_bytes(), subprocess.check_output(
                ['git', '-C', str(build.LIBC), 'show', 'HEAD:' + str(path.relative_to(build.LIBC))]))
        for command in r['commands']:
            if '-MF' in command['command']: self.assertIn('-D_FORTIFY_SOURCE=0', command['command'])
        self.assertTrue(r['consumer_flags_unchanged'])
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)

    def test_native_exact_bounds_zero_length_nonterminated_and_original_fatal_paths(self):
        result = subprocess.run([str(PACKAGE / 'host-strncpy-chk')], capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        native_map = (PACKAGE / 'native.map').read_text()
        for owner, name in ((2, '__strncpy_chk'), (3, 'stpncpy'), (4, '__chk_overlap'),
                            (4, '__chk_fail_overflow'), (5, '_os_crash')):
            self.assertRegex(native_map, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s+' + str(owner) + r'\] _fixture_' + name + '$')
        self.assertTrue(self.report['original_bounds_checked_before_copy'])
        self.assertTrue(self.report['original_overlap_after_padding_write_observed'])
        self.assertFalse(self.report['overlap_prewrite_safety_claimed'])

    def test_nonempty_overlap_records_actual_native_diagnostic_without_safety_claim(self):
        result = subprocess.run([str(PACKAGE / 'host-strncpy-chk'), 'nonempty-overlap'],
                                capture_output=True, text=True, timeout=20)
        if self.report['native_nonempty_overlap_original_trap_after_write_observed']:
            self.assertIn(result.returncode, (-signal.SIGILL, -signal.SIGTRAP))
            self.assertEqual((result.stdout, result.stderr), (build.OVERLAP, ''))
            self.assertFalse(self.report['native_nonempty_overlap_asan_rejection_observed'])
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('AddressSanitizer: memcpy-param-overlap', result.stderr)
        self.assertTrue(self.report['original_overlap_checked_after_copy'])

    def test_actual_a76_prewrite_bounds_no_provider_recursion_and_original_leaf_calls(self):
        checked = macho.MachO(Path(self.report['objects']['strncpy_chk']))
        at = checked.names['___strncpy_chk']['address']
        self.assertEqual(struct.unpack('<2I', checked.at(at + 12, 8)), (0xeb02007f, 0x540000e3))
        public = checked.function('___strncpy_chk')['relocations']
        self.assertEqual(public, [(44, 0x2d, '___chk_fail_overflow'), (24, 0x2d, '___strncpy_chk.cold.1')])
        cold = checked.function('___strncpy_chk.cold.1')['relocations']
        self.assertIn((28, 0x2d, '_stpncpy'), cold)
        self.assertIn((84, 0x2d, '___chk_overlap'), cold)
        self.assertNotIn('___strncpy_chk', {target for _, _, target in public + cold})
        leaf = macho.MachO(Path(self.report['objects']['stpncpy']))
        self.assertEqual(leaf.function('_stpncpy')['relocations'],
            [(108, 0x2d, '_memcpy'), (88, 0x2d, '_memset'), (68, 0x2d, '_memcpy'), (40, 0x2d, '_strnlen')])
        for command in self.report['commands']:
            if command['stdout'].endswith('-compile.stdout') and '/target-' in command['stdout']:
                self.assertIn('-mcpu=cortex-a76', command['command'])

    def test_exact_full_client_link_delta_zero_new_prerequisites_and_duplicates(self):
        r = self.report
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(r['previous_missing_count'], 50); self.assertEqual(len(missing), 49)
        self.assertEqual(r['closed_symbols'], ['___strncpy_chk'])
        self.assertEqual(r['newly_reachable_symbols'], []); self.assertEqual(r['target_duplicate_symbols'], [])
        base = json.loads((build.BASE / 'manifest.json').read_text())
        old = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new = list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'): old[old.index(flag) + 1] = new[new.index(flag) + 1]
        self.assertEqual(new, old + [r['target_archive']])
        self.assertTrue(r['original_openssh_config_unchanged'])
        for key in ('target_link_complete', 'target_executed', 'accepted_runtime_modified', 'provider_stubs',
                    'host_account_files_accessed', 'network_services_executed'):
            self.assertFalse(r[key])


if __name__ == '__main__': unittest.main()
