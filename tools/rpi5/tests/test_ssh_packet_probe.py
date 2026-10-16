# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_apple_ssh_packet_probe as builder


class PacketProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = builder.ROOT / 'build/rpi5/apple-ssh-packet-v9xoz8gd'
        cls.report = json.loads((cls.package / 'manifest.json').read_text())

    def test_exact_inputs_and_explicit_target_gap(self):
        for field in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in self.report[field].items():
                self.assertEqual(builder.sha(Path(name)), digest, name)
        self.assertFalse(self.report['target_link_complete'])
        self.assertFalse(self.report['pi_execution'])
        for name in ('EVP_CIPHER_CTX_free', 'EVP_CIPHER_CTX_get_iv_length', 'EVP_CIPHER_CTX_new',
                     'EVP_Cipher', 'EVP_CipherInit', 'EVP_chacha20', 'memset_s', 'timingsafe_bcmp'):
            self.assertIn('"_' + name + '"', self.report['target_link_error'])

    def test_actual_original_packet_cipher_with_host_crypto(self):
        run = subprocess.run([self.package / 'sshpacketprobe-host'], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, self.report['host_stdout'])
        self.assertEqual(run.stderr, '')

    def test_missing_tampering_fails_the_rejection_oracle(self):
        original = builder.SOURCE.read_text()
        self.assertEqual(original.count('mutated[j] ^= 1;'), 1)
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); source = work / 'probe.c'; program = work / 'probe'
            source.write_text(original.replace('mutated[j] ^= 1;', 'mutated[j] ^= 0;'))
            command = next(r['command'] for r in self.report['commands'] if r['stdout'].endswith('/probe-native.stdout'))
            flags = command[:command.index('-MD')]
            host_objects = [self.package / (name + '-native.o') for name in
                            ('cipher-chachapoly-libcrypto', 'timingsafe_bcmp', 'freezero', 'explicit_bzero')]
            compiled = subprocess.run(flags + [str(source), *map(str, host_objects),
                str(builder.BASE / 'poly1305.c.native.o'), str(builder.CRYPTO), '-o', str(program)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([program], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(run.stdout, 'RPI5XNU:SSHPACKET:FAIL\n')
            self.assertEqual(run.stderr, '')


if __name__ == '__main__':
    unittest.main()
