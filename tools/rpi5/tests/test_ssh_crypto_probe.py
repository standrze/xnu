# SPDX-License-Identifier: BSD-2-Clause
"""Existing-package checks and negative KAT controls; no Pi or target execution."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import build_apple_ssh_crypto_probe as build
from tools.rpi5.prepare_pid1 import inspect


class CryptoProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ.get('RPI5_SSH_CRYPTO_PROBE',
            str(build.ROOT / 'build/rpi5/apple-ssh-crypto-_qsv492k')))
        cls.report = json.loads((cls.package / 'manifest.json').read_text())
        cls.work = Path(tempfile.mkdtemp(prefix='ssh-crypto-controls-', dir=build.ROOT / 'build/rpi5'))

    def test_actual_inputs_and_static_target(self):
        for field in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for path, digest in self.report[field].items():
                self.assertEqual(build.sha(Path(path)), digest, path)
        program = Path(self.report['actual_static_executable'])
        self.assertEqual(inspect(program.read_bytes()), self.report['macho_audit'])
        self.assertTrue(self.report['static_link_complete'])
        self.assertEqual(self.report['undefined_symbols'], [])
        self.assertFalse(self.report['pi_executed'])

    def test_native_sanitized_kats(self):
        result = subprocess.run([self.package / 'sshcryptoprobe-host'], capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.report['native_stdout'])
        self.assertEqual(result.stderr, '')

    def test_bad_vectors_are_rejected(self):
        original = build.SOURCE.read_text()
        compile_row = next(r['command'] for r in self.report['commands']
            if '-c' in r['command'] and str(build.SOURCE) in r['command']
            and '-Dmain=darwin_network_command_main' not in r['command'])
        flags = compile_row[:compile_row.index('-MD')]
        for label, old, new in (('chacha', '76b8e0ad', '77b8e0ad'),
                                ('poly1305', 'a8061dc1', 'a9061dc1')):
            with self.subTest(label=label):
                self.assertEqual(original.count(old), 1)
                source, program = self.work / (label + '.c'), self.work / label
                source.write_text(original.replace(old, new))
                command = flags + [str(source),
                    str(self.package / 'chacha.c.native.o'),
                    str(self.package / 'poly1305.c.native.o'), '-o', str(program)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([program], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('RPI5XNU:SSHCRYPTO:FAIL NO_SECURITY_CLAIM', result.stdout)
                self.assertNotIn('RPI5XNU:SSHCRYPTO:PASS', result.stdout)
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
