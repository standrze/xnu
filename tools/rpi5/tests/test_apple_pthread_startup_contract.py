# SPDX-License-Identifier: BSD-2-Clause
"""Frozen private runtime evidence; no uninitialized target executable is run."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = {
    'wait': ('apple-pthread-wait-if5o744t',
             '394565fbae712065b2a09adbdde6eb681ddc3045562ba3c5ccb62fcbbc95b23d'),
    'target': ('apple-pthread-bcm2712-qualified-x9kp1ral',
               'a1f0a4a25efad30a2fb152e5c3a0b0797348deea88786bb28546310ca9e1f00b'),
    'config': ('apple-pthread-bcm2712-check-kgbwgqa0',
               '7b377e6b732a8da13f74fa1f0500ed3ebbe9c6962ed5d8da65ac52b0a6626c8b'),
    'contract': ('apple-pthread-startup-contract-t9v7gpfa',
                 'fc8db3c791f55b0286b12ef38cd2a412b525af7c62400771a8e5a2c86d5ac325'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dep_paths(path):
    raw = Path(path).read_text().replace('\\\n', ' ').partition(':')[2]
    return {str(Path(p).resolve()) for p in shlex.split(raw)}


def validate_closure(package, report):
    actual_generated = {str(p) for p in package.rglob('*')
                        if p.is_file() and p != package / 'manifest.json'}
    if actual_generated != set(report['generated_sha256']):
        raise ValueError('Generated membership mismatch')
    observed = set()
    for path in package.glob('*.d'):
        observed.update(dep_paths(path))
    # -H may name an SDK symlink while the .d scanner resolves its target.
    claimed = {str(Path(p).resolve()) for p in report['headers_sha256']}
    if observed != claimed:
        raise ValueError('Consumed dependency membership mismatch')
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for path, expected in report[key].items():
            if sha(path) != expected:
                raise ValueError('Input drift: ' + path)


class ApplePthreadStartupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages = {key: ROOT / 'build/rpi5' / value[0]
                        for key, value in PACKAGES.items()}
        cls.reports = {key: json.loads((path / 'manifest.json').read_text())
                       for key, path in cls.packages.items()}

    def test_frozen_inputs_and_actual_complete_dependency_membership(self):
        for key, package in self.packages.items():
            self.assertEqual(sha(package / 'manifest.json'), PACKAGES[key][1])
            validate_closure(package, self.reports[key])
        target = self.reports['target']
        for unit in target['units']:
            self.assertTrue(unit['compiled'])
            actual = dep_paths(self.packages['target'] / (unit['label'] + '.d'))
            self.assertEqual(actual, set(unit['actual_headers_sha256']))
            self.assertEqual(unit['actual_headers_sha256'], unit['preprocessor_headers_sha256'])

    def test_membership_deletion_is_not_accepted_as_provenance(self):
        package = self.packages['contract']
        for key in ('headers_sha256', 'generated_sha256'):
            tampered = copy.deepcopy(self.reports['contract'])
            tampered[key].pop(next(iter(tampered[key])))
            with self.assertRaisesRegex(ValueError, 'membership mismatch'):
                validate_closure(package, tampered)

    def test_real_wait_traps_and_kernel_error_behavior_host_only(self):
        package, report = self.packages['wait'], self.reports['wait']
        proc = subprocess.run([package / 'pthread-wait-host'], capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, report['native_stdout'])
        self.assertIn('REAL_ERRORS=96000 TIMEOUTS=2 WAKE=1 PSYNCH_NOT_EXECUTED HOST_ONLY', proc.stdout)
        self.assertFalse(report['host_psynch_executed'])
        self.assertFalse(report['target_errno_kernel_semantics_executed'])
        disassembly = (package / 'target-disassembly.stdout').read_text()
        self.assertEqual(disassembly.count('svc\t#0x80'), 5)
        relocations = subprocess.check_output(
            ['xcrun', 'otool', '-rv', package / 'target.o'], text=True)
        self.assertEqual(relocations.count('_cerror_nocancel'), 5)
        for number in report['syscall_numbers'].values():
            self.assertIn('mov\tx16, #' + hex(number), disassembly)
        self.assertEqual(report['syscall_numbers'], {
            'psynch_mutexwait': 301, 'psynch_mutexdrop': 302,
            'ulock_wait': 515, 'ulock_wait2': 544, 'ulock_wake': 516})

    def test_actual_15_units_explicit_capability_not_fake_protection(self):
        report = self.reports['target']
        self.assertEqual(report['compiled_units'], 15)
        self.assertEqual(report['attempted_units'], 15)
        self.assertFalse(report['config_preserved'])
        self.assertTrue(report['original_implementation_sources_preserved'])
        config = report['target_configuration']
        original = Path(config['original']).read_text()
        self.assertEqual(Path(config['derived']).read_text(),
                         original.replace(config['exact_replacement'], config['replacement']))
        self.assertFalse(config['kernel_vm_protection_changed'])
        self.assertFalse(config['per_thread_jit_protection_supported'])
        self.assertFalse(config['mte_supported'])
        members = subprocess.check_output(['xcrun', 'ar', 't', report['partial_archive']], text=True).splitlines()
        self.assertEqual(members[1:], [Path(u['object']).name for u in report['units']])
        for copied, row in report['original_header_installations'].items():
            self.assertEqual(Path(copied).read_bytes(), Path(row['source']).read_bytes())
        for row in report['commands']:
            if row['stdout'].endswith('/platform-lock-compile.stdout'):
                self.assertIn('-DCONFIG_MTE=0', row['command'])
                self.assertIn('-mcpu=cortex-a76', row['command'])
        capability = (ROOT / 'tools/rpi5/user/pthread_bcm2712_capabilities.h').read_text()
        self.assertEqual(capability.count('__builtin_trap()'), 2)

    def test_original_public_unsupported_jit_and_abort_wrapper_failures(self):
        for package_key, executable, expected_key in (
                ('config', 'jit-unsupported-host', 'unsupported_native_stdout'),
                ('contract', 'abort-wrapper-host', 'host_abort_wrapper_stdout')):
            proc = subprocess.run([self.packages[package_key] / executable],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, '')
            self.assertEqual(proc.stdout, self.reports[package_key][expected_key])
        report = self.reports['config']
        original = Path(self.reports['target']['units'][0]['source']).read_text()
        for body in report['exact_original_public_functions'].values():
            self.assertIn(body, original)
        self.assertTrue(self.reports['contract']['abort_test_simulated_endpoints'])
        self.assertTrue(self.reports['contract']['original_abort_signal_and_fallback_preserved'])

    def test_real_registration_abi_and_main_startup_remains_unqualified(self):
        report = self.reports['contract']
        self.assertTrue(report['actual_a76_static_assertions'])
        self.assertTrue(report['kernel_user_registration_layout_equal'])
        self.assertEqual(report['actual_layout']['pthread_bytes'], 6368)
        self.assertEqual(report['actual_layout']['pthread_tsd_offset'], 224)
        self.assertEqual(report['actual_layout']['registration_bytes'], 56)
        self.assertEqual(len(report['registration_fields']), 10)
        source = (self.packages['contract'] / 'layout-target.c').read_text()
        self.assertEqual(source.count('"A76 '), len(report['actual_layout']))
        proc = subprocess.run([self.packages['contract'] / 'layout-host'],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        values = dict((k, int(v)) for k, v in
                      (line.split('=') for line in proc.stdout.splitlines()))
        self.assertEqual(values, report['actual_layout'])
        links = self.reports['config']['link_results']
        self.assertTrue(links['packet-uninitialized']['complete'])
        self.assertEqual(links['packet-uninitialized']['duplicates'], ['_memcpy', '_memset'])
        self.assertFalse(links['init-live']['complete'])
        self.assertEqual(links['init-live']['missing'], [
            '___bsdthread_register', '___exit', '___workq_open', '__os_xbs_chrooted',
            '__platform_bzero', '__platform_memset', '__platform_strlen', '_host_info',
            '_mach_host_self', '_mach_port_construct', '_mach_port_deallocate',
            '_mach_thread_self', '_start_wqthread', '_thread_start'])
        for report in self.reports.values():
            self.assertFalse(report['pi_executed'])
            for key in ('target_main_thread_initialized', 'target_startup_created',
                        'target_pthread_initialized', 'pthread_runtime_qualified', 'executable_run'):
                self.assertFalse(report.get(key, False))


if __name__ == '__main__':
    unittest.main()
