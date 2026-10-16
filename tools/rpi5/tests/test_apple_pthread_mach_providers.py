# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure, dep_paths

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = {
    'mach': ('apple-pthread-mach-linkable-9lq6yta2', '96e38dda4d72ea8cdfe7d5a9e318dab08ed4a0a02b99eb7d11709d55ab3096af'),
    'host': ('apple-pthread-mach-check-e5pbtcuc', '17a4143bdf7d6e2f089df83b564a39a9efb6195d8013d785ee22b02b8e7a6627'),
    'messaging': ('apple-pthread-messaging-headers-mubxo_kh', '77d1fa636ab6307ff46d0b014c0211f2695b2f3090d2fe8e2b65734fb4cd8265'),
}


class ApplePthreadMachProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {key: ROOT / 'build/rpi5' / value[0] for key, value in PACKAGES.items()}
        cls.reports = {key: json.loads((path / 'manifest.json').read_text()) for key, path in cls.paths.items()}

    def test_complete_source_consumed_generated_membership_and_original_headers(self):
        for key, package in self.paths.items():
            report = self.reports[key]
            self.assertEqual(sha(package / 'manifest.json'), PACKAGES[key][1])
            validate_closure(package, report)
            for path, record in report.get('original_header_installations', {}).items():
                self.assertEqual(Path(path).read_bytes(), Path(record['source']).read_bytes())
            for unit in report.get('units', []):
                self.assertTrue(unit['compiled'])
                self.assertEqual(unit['actual_headers_sha256'], unit['preprocessor_headers_sha256'])
                self.assertEqual(dep_paths(package / (unit['label'] + '.d')), set(unit['actual_headers_sha256']))

    def test_genuine_mig_host_caller_real_kernel_and_failures(self):
        report = self.reports['host']
        proc = subprocess.run([self.paths['host'] / 'mig-host-info'], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, report['native_stdout'])
        self.assertIn('REAL_KERNEL_CASES=24', proc.stdout)
        self.assertTrue(report['real_host_kernel'])
        self.assertTrue(report['native_asan_ubsan'])
        self.assertTrue(report['no_target_implementation_changes'])

    def test_real_trap_table_thread_entry_and_mig_generation(self):
        self.assertEqual(self.reports['mach']['compiled_units'], 8)
        self.assertEqual(self.reports['messaging']['compiled_units'], 17)
        package = self.paths['messaging']
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', package / 'mach-traps.o'], text=True)
        for symbol in ('_host_self_trap', '_thread_self_trap', '_mach_msg2_trap',
                       '__kernelrpc_mach_port_construct_trap', '__kernelrpc_mach_port_deallocate_trap'):
            self.assertRegex(symbols, r'(?m)^[0-9a-f]+ T ' + symbol + '$')
        entry = subprocess.check_output(['xcrun', 'nm', '-g', package / 'pthread-asm.o'], text=True)
        for symbol in ('_start_wqthread', '_thread_start'):
            self.assertRegex(entry, r'(?m)^[0-9a-f]+ T ' + symbol + '$')
        self.assertIn(' U __pthread_wqthread', entry)
        self.assertIn(' U __pthread_start', entry)
        report = self.reports['messaging']
        self.assertEqual([r['name'] for r in report['migrations']], ['mach_host', 'mach_port', 'task'])
        self.assertTrue(all(r['generated'] for r in report['migrations']))
        for migration in report['migrations']:
            actual = dep_paths(package / (migration['name'] + '-mig.d'))
            self.assertEqual(actual, set(migration['input_dependencies']))
        source = (package / 'mach_hostUser.c').read_text()
        self.assertIn('MIG_REPLY_MISMATCH', source)
        self.assertIn('MIG_TYPE_ERROR', source)
        self.assertIn('MIG_ARRAY_TOO_LARGE', source)

    def test_actual_init_and_original_logging_stay_live_and_incomplete(self):
        report = self.reports['messaging']
        self.assertEqual(report['target_missing_symbols'], [
            '___sendto', '__platform_strlcpy', '_close$NOCANCEL', '_connect$NOCANCEL',
            '_fcntl$NOCANCEL', '_mach_continuous_time', '_mach_vm_deallocate',
            '_mach_vm_map', '_proc_pidinfo', '_socket'])
        self.assertEqual(report['target_duplicate_symbols'], [])
        self.assertTrue(report['real_libkernel_init_forced_live'])
        self.assertTrue(report['real_pthread_init_forced_live'])
        self.assertTrue(report['original_implementation_bodies_unchanged'])
        for key in ('target_link_complete', 'source_configuration_weakened',
                    'target_startup_created', 'target_main_thread_initialized',
                    'native_runtime_tested', 'accepted_runtime_modified', 'pi_executed'):
            self.assertFalse(report[key])
        self.assertFalse((self.paths['messaging'] / 'NOT_RUN_init-live').exists())
        # The state comes from the original libkernel object, not a fake global.
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.paths['messaging'] / 'libkernel-init.o'], text=True)
        self.assertRegex(symbols, r'(?m)^[0-9a-f]+ S __os_xbs_chrooted$')


if __name__ == '__main__': unittest.main()
