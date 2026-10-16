# SPDX-License-Identifier: BSD-2-Clause
"""Offline original-pthread bootstrap/linked-kernel contract, never target execution."""
import copy
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import unittest

from tools.rpi5.check_apple_pthread_kernel_contract import MachO, KERNEL
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = {
    'dyld': ('apple-pthread-dyld-bootstrap-sskvb3j8',
             '75bae2177d2e9d6f93edffdfc1531699538188a5e5a51cde9d231daae88289f9'),
    'kernel': ('apple-pthread-kernel-tsd-contract-fifml3xs',
               '52e1a54657775a7b3712a2781501f65b9c8a7f5df8730528037e14fca0cbaef7'),
}


def kernel_closure(package, report):
    generated = {str(p) for p in package.rglob('*')
                 if p.is_file() and p != package / 'manifest.json'}
    if generated != set(report['generated_sha256']):
        raise ValueError('Generated membership mismatch')
    actual_headers, dependency_files = set(), set()
    for record in report['commands']:
        command = record['command']
        if '-MF' not in command:
            continue
        dep = Path(command[command.index('-MF') + 1])
        dependency_files.add(dep)
        raw = dep.read_text().replace('\\\n', ' ').partition(':')[2]
        # The kernel compile database deliberately uses build-directory-relative
        # headers. The test runner's cwd is not their compile cwd.
        actual_headers.update(str((Path(record['cwd']) / p).resolve())
                              for p in shlex.split(raw))
    if dependency_files != set(package.glob('*.d')):
        raise ValueError('Compile dependency file membership mismatch')
    if actual_headers != {str(Path(p).resolve()) for p in report['headers_sha256']}:
        raise ValueError('Consumed header membership mismatch')
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for path, digest in report[key].items():
            if sha(path) != digest:
                raise ValueError('Input drift: ' + path)


class ApplePthreadDyldContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {k: ROOT / 'build/rpi5' / v[0] for k, v in PACKAGES.items()}
        cls.reports = {k: json.loads((p / 'manifest.json').read_text())
                       for k, p in cls.paths.items()}

    def test_frozen_closure_and_real_compile_directory_dependencies(self):
        for key, path in self.paths.items():
            self.assertEqual(sha(path / 'manifest.json'), PACKAGES[key][1])
        validate_closure(self.paths['dyld'], self.reports['dyld'])
        kernel_closure(self.paths['kernel'], self.reports['kernel'])
        self.assertEqual(len(list(self.paths['kernel'].glob('*.d'))), 6)
        for key in ('headers_sha256', 'generated_sha256'):
            tampered = copy.deepcopy(self.reports['kernel'])
            tampered[key].pop(next(iter(tampered[key])))
            with self.assertRaisesRegex(ValueError, 'membership mismatch'):
                kernel_closure(self.paths['kernel'], tampered)

    def test_original_bootstrap_namespaced_and_only_mach_init_replaced(self):
        path, report = self.paths['dyld'], self.reports['dyld']
        pattern = r'^[0-9a-f]+ [A-Z] _([a-zA-Z_][a-zA-Z_0-9]*)$'
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', path / 'dyld-scoped.o'], text=True)
        actual = set(re.findall(pattern, symbols, re.M))
        self.assertEqual(actual, {'rpi5_dyld_' + n for n in report['namespaced_original_definitions']})
        self.assertIn('rpi5_dyld__main_thread', actual)
        self.assertIn('rpi5_dyld__pthread_set_self', actual)
        before, after = (report[k] for k in
                         ('original_mach_archive_members_sha256', 'private_mach_archive_members_sha256'))
        self.assertEqual(set(before), set(after))
        self.assertEqual({n for n in before if before[n] != after[n]}, {'mach_init.o'})
        undefined = subprocess.check_output(['xcrun', 'nm', '-u', path / 'mach-init-dyld.o'], text=True).splitlines()
        self.assertIn('_rpi5_dyld__pthread_set_self', undefined)
        self.assertNotIn('__pthread_set_self', undefined)
        linked = subprocess.check_output(['xcrun', 'llvm-objdump',
            '--disassemble-symbols=_mach_init_doit', path / 'NOT_RUN_init-live'], text=True)
        self.assertRegex(linked, r'\bb\s+0x[0-9a-f]+ <_rpi5_dyld__pthread_set_self>')
        self.assertEqual(subprocess.check_output(
            ['xcrun', 'nm', '-u', path / 'NOT_RUN_init-live'], text=True).strip(), '')
        self.assertTrue(report['normal_pthread_apis_remain_normal_variant'])
        self.assertEqual(report['target_duplicate_symbols'], [])

    def test_nine_actual_linked_kernel_functions_match_recompiled_bytes_and_relocations(self):
        report = self.reports['kernel']
        expected = {'_exec_add_apple_strings', '_exec_add_entropy_key', '_load_unixthread',
                    '_bsdthread_register', '_user_cont_hwclock_allowed', '_user_timebase_type',
                    '_platform_syscall', '_thread_set_cthread_self', '_machine_thread_set_tsd_base'}
        rows = report['exact_recompiled_function_comparisons']
        self.assertEqual({r['name'] for r in rows}, expected)
        self.assertEqual(len(rows), len(expected))
        parsed = {}
        for row in rows:
            observed = []
            for key in ('object', 'recompiled'):
                path = row[key]
                if path not in parsed:
                    parsed[path] = MachO(path)
                observed.append(parsed[path].function(row['name']))
            self.assertEqual(observed[0], observed[1], row['name'])
            # JSON turns tuples into lists; compare through canonical JSON shape.
            retained = {k: row[k] for k in ('bytes', 'sha256', 'relocations')}
            self.assertEqual(json.loads(json.dumps(observed[0])), retained)
        self.assertTrue(report['actual_kernel_tsd_syscall_recompiled'])

    def test_real_kernel_dispatch_features_and_no_runtime_claim(self):
        report = self.reports['kernel']
        kernel_manifest = json.loads((KERNEL / 'manifest.json').read_text())
        binary = Path(kernel_manifest['kernel'])
        self.assertEqual(sha(binary), report['kernel_sha256'])
        image = MachO(binary)
        table = image.names['_pthread_internal_functions']['address']
        self.assertEqual(struct.unpack('<I', image.at(table, 4))[0], 0)
        registration = struct.unpack('<Q', image.at(table + 0x58, 8))[0]
        self.assertEqual(registration, image.names['__bsdthread_register']['address'])
        self.assertEqual(hex(registration), report['actual_registration_entry'])
        self.assertEqual(int(report['actual_provider_feature_mask'], 16), 0x400001df)
        for feature in report['required_user_features'].values():
            self.assertEqual(0x400001df & feature, feature)
        self.assertEqual(image.at(image.names['_user_cont_hwclock_allowed']['address'], 8),
                         bytes.fromhex('e0031f2ac0035fd6'))
        self.assertEqual(image.at(image.names['_user_timebase_type']['address'], 8),
                         bytes.fromhex('20008052c0035fd6'))
        for result in self.reports.values():
            for key in ('pi_executed', 'target_startup_created', 'target_main_thread_initialized'):
                self.assertIs(result[key], False)
        for key in ('entropy_qualified', 'kernel_api_runtime_executed', 'pthread_registration_runtime_executed'):
            self.assertIs(report[key], False)
        self.assertIs(self.reports['dyld']['constructors_order_wired'], False)
        self.assertIs(self.reports['dyld']['accepted_runtime_modified'], False)


if __name__ == '__main__':
    unittest.main()
