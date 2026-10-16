# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import build_apple_sysctl_runtime as builder


class AppleSysctlRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = builder.ROOT / 'build/rpi5/apple-sysctl-runtime-nfhrya57'
        cls.report = json.loads((cls.package / 'manifest.json').read_text())

    def test_pins_and_actual_dependency_closure(self):
        self.assertEqual(builder.sha(self.package / 'manifest.json'),
            '6f42910a9bce37cd42d43a4febadee40498edd57c484d0312048c6a34413bd91')
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for path, digest in self.report[key].items():
                self.assertEqual(builder.sha(Path(path)), digest, path)
        actual = set()
        for path in self.package.glob('*.d'):
            actual.update(str(Path(p).resolve()) for p in
                shlex.split(path.read_text().replace('\\\n', ' ').partition(':')[2]))
        self.assertEqual(actual, set(self.report['headers_sha256']))
        self.assertEqual(set(self.report['generated_sha256']),
            {str(p) for p in self.package.iterdir() if p.is_file() and p.name != 'manifest.json'})

    def test_real_host_concurrency_errors_and_features(self):
        result = subprocess.run([self.package / 'sysctlbyname-host'],
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['host_stdout'])
        self.assertIn('QUERIES=16000 INJECTED=12 FEATURES=6', result.stdout)
        self.assertEqual(self.report['host_native_concurrency_threads'], 8)

    def test_genuine_trap_and_errno_not_feature_shim(self):
        disassembly = subprocess.check_output(['xcrun', 'otool', '-tvV',
            self.package / 'syscall-target.o'], text=True)
        self.assertRegex(disassembly, r'mov\s+x16, #0xca')
        self.assertRegex(disassembly, r'svc\s+#0x80')
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.report['target_archive']], text=True)
        for name in ('_sysctlbyname', '___sysctl'):
            self.assertEqual(len(re.findall(r'^[0-9a-f]+ T ' + name + '$', symbols, re.M)), 1)
        self.assertIn(' U _cerror_nocancel', symbols)
        self.assertNotRegex(symbols, r'T _pthread_')

    def test_static_four_pthread_gaps_remain_honest(self):
        self.assertEqual(self.report['target_missing_symbols'], builder.EXPECTED_GAPS)
        self.assertFalse((self.package / 'sshpacketprobe').exists())
        for key in ('target_link_complete', 'pthread_provider_implemented',
                    'constructors_executed_on_pi', 'cpu_features_verified_on_pi', 'installed', 'pi_executed'):
            self.assertFalse(self.report[key])
        self.assertTrue(self.report['original_apple_sysctlbyname_unchanged'])


if __name__ == '__main__': unittest.main()
