# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import check_apple_pthread_platform_build as builder


class ApplePthreadPlatformBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((builder.BASE / 'manifest.json').read_text())
        cls.package = builder.ROOT / 'build/rpi5/apple-pthread-platform-check-m7im0unk'
        cls.report = json.loads((cls.package / 'manifest.json').read_text())

    def test_all_frozen_original_generated_and_consumed_inputs(self):
        self.assertEqual(builder.sha(builder.BASE / 'manifest.json'), builder.BASE_SHA)
        self.assertEqual(builder.sha(self.package / 'manifest.json'),
            '463cdcb6bd64b4cecb756ed1886288bb81b116a1ab3592ffa987a67dc0c2d6dd')
        for report in (self.base, self.report):
            for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
                for path, digest in report[key].items():
                    self.assertEqual(builder.sha(path), digest, path)
        for package, report in ((builder.BASE, self.base), (self.package, self.report)):
            self.assertEqual(set(report['generated_sha256']),
                {str(p) for p in package.rglob('*') if p.is_file() and p != package / 'manifest.json'})
        for unit in self.base['units']:
            if not unit['compiled']: continue
            dep = builder.BASE / (unit['label'] + '.d')
            paths = {str(Path(p).resolve()) for p in shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2])}
            self.assertEqual(paths, set(unit['actual_headers_sha256']))
            self.assertEqual(unit['actual_headers_sha256'], unit['preprocessor_headers_sha256'])
        native = set()
        for dep in self.package.glob('*.d'):
            native.update(str(Path(p).resolve()) for p in shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2]))
        self.assertEqual(native, set(self.report['headers_sha256']))

    def test_partial_archive_honestly_excludes_uncompiled_main(self):
        self.assertEqual(self.base['compiled_units'], 14)
        self.assertEqual(self.base['attempted_units'], 15)
        self.assertEqual([u['label'] for u in self.base['units'] if not u['compiled']], ['pthread-pthread'])
        members = subprocess.check_output(['xcrun', 'ar', 't', self.base['partial_archive']], text=True).splitlines()
        self.assertEqual(members[0], '__.SYMDEF SORTED')
        self.assertEqual(members[1:], [Path(u['object']).name for u in self.base['units'] if u['compiled']])
        self.assertNotIn('pthread-pthread.o', members)
        diagnostics = '\n'.join(self.base['units'][0]['diagnostics'])
        self.assertIn('os_thread_self_restrict_rwx_is_supported', diagnostics)
        self.assertIn('kqueue_id_t', diagnostics)
        for copied, row in self.base['original_header_installations'].items():
            self.assertFalse(row['modified'])
            self.assertEqual(Path(copied).read_bytes(), Path(row['source']).read_bytes())

    def test_native_original_platform_concurrency_and_failures(self):
        result = subprocess.run([self.package / 'apple-platform-host'], text=True,
            capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['native_stdout'])
        self.assertIn('THREADS=8 LOCKED=160000 ATOMIC=160000 ONCE=1 SEMAPHORE=8 FAILURE_CASES=3', result.stdout)
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.package / 'platform-lock-native.o'], text=True)
        self.assertRegex(symbols, r' T _rpi5_native_os_unfair_lock_lock\n')
        self.assertRegex(symbols, r' T _rpi5_native__os_once\n')
        self.assertNotRegex(symbols, r' T _os_unfair_lock_lock\n')
        self.assertIn(' U ___ulock_wait', symbols)
        self.assertTrue(self.report['host_real_pthread_and_mach_services'])
        self.assertFalse(self.report['native_pthread_implementation_tested'])

    def test_original_mutex_tsd_config_and_remaining_link_contract(self):
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.base['partial_archive']], text=True)
        for name in ('_pthread_mutex_lock', '_pthread_mutex_unlock', '_pthread_self', '__os_once'):
            self.assertEqual(len(re.findall(r'^[0-9a-f]+ T ' + name + '$', symbols, re.M)), 1)
        self.assertEqual(self.report['target_missing_symbols'], [
            '___psynch_mutexdrop', '___psynch_mutexwait', '___ulock_wait', '___ulock_wait2',
            '___ulock_wake', '__pthread_ptr_munge_token', '_abort_with_reason', '_pthread_equal'])
        self.assertEqual(self.report['target_duplicate_symbols'], [])
        self.assertFalse((self.package / 'sshpacketprobe').exists())
        for key in ('target_link_complete', 'target_main_pthread_compiles', 'pthread_runtime_qualified',
                    'accepted_startup_modified', 'installed', 'pi_executed'):
            self.assertFalse(self.report[key])
        for command in self.base['commands']:
            argv = command['command']
            if command['stdout'].endswith('/platform-lock-compile.stdout'):
                self.assertIn('-DCONFIG_MTE=1', argv)
                self.assertIn('-mcpu=cortex-a76', argv)
            self.assertFalse(any('_PTHREAD_CONFIG_JIT_WRITE_PROTECT=0' in str(x) for x in argv))


if __name__ == '__main__': unittest.main()
