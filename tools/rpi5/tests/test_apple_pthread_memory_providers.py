# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'build/rpi5/apple-pthread-memory-4idfg5qr'
MANIFEST_SHA = 'd229d0b2854d70b36515fc421912866067079d329e4e4bc4cb77463e0bbaa8f1'


class ApplePthreadMemoryProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_all_frozen_generated_and_consumed_inputs(self):
        self.assertEqual(sha(PACKAGE / 'manifest.json'), MANIFEST_SHA)
        validate_closure(PACKAGE, self.report)
        self.assertEqual(sha(self.report['target_archive']), self.report['target_archive_sha256'])
        self.assertEqual(sha(self.report['scoped_pthread_archive']), self.report['scoped_pthread_archive_sha256'])

    def test_original_memory_boundaries_overlap_guarded_strings_and_real_exit(self):
        proc = subprocess.run([PACKAGE / 'memory-provider-host'],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, self.report['native_stdout'])
        self.assertIn('CASES=131584 GUARDED_STRLEN=2048 REAL_EXIT=37', proc.stdout)
        self.assertIn('REGISTRATION_NOT_EXECUTED WORKQ_NOT_EXECUTED HOST_ONLY', proc.stdout)

    def test_private_scope_changes_only_three_definition_identifiers(self):
        original = Path(self.report['original_pthread_source']).read_text()
        scoped = Path(self.report['scoped_pthread_source']).read_text()
        boundary = original.index('#pragma mark libplatform shims')
        expected = original[boundary:]
        for name, renamed in self.report['private_wrapper_renames'].items():
            expected, count = re.subn(r'(?m)^' + name + r'\(', renamed + '(', expected)
            self.assertEqual(count, 1)
        self.assertEqual(scoped, original[:boundary] + expected)
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', PACKAGE / 'pthread-private.o'], text=True)
        for name in ('memset', 'memcpy', 'bzero'):
            self.assertNotRegex(symbols, r'^[0-9a-f]+ [Tt] _' + name + '$')
            self.assertIn('_rpi5_pthread_private_' + name, symbols)
        self.assertEqual(self.report['target_duplicate_symbols'], [])

    def test_original_three_traps_and_eight_genuine_remaining_dependencies(self):
        disassembly = (PACKAGE / 'target-trap-disassembly.stdout').read_text()
        relocations = (PACKAGE / 'target-trap-relocations.stdout').read_text()
        self.assertEqual(disassembly.count('svc\t#0x80'), 3)
        self.assertEqual(relocations.count('_cerror_nocancel'), 3)
        for number in self.report['syscall_numbers'].values():
            self.assertIn('mov\tx16, #' + hex(number), disassembly)
        self.assertEqual(self.report['target_missing_symbols'], [
            '__os_xbs_chrooted', '_host_info', '_mach_host_self', '_mach_port_construct',
            '_mach_port_deallocate', '_mach_thread_self', '_start_wqthread', '_thread_start'])
        self.assertFalse((PACKAGE / 'NOT_RUN_init-live').exists())
        for field in ('host_registration_executed', 'host_workqueue_executed',
                      'target_main_thread_initialized', 'target_startup_created',
                      'accepted_runtime_modified', 'pi_executed'):
            self.assertFalse(self.report[field])


if __name__ == '__main__':
    unittest.main()
