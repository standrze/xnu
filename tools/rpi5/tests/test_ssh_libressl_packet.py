# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_libressl_packet as builder


class GenuineLibreSSLPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = builder.ROOT / 'build/rpi5/apple-ssh-libressl-packet-9ws4lrfd'
        cls.report = json.loads((cls.package / 'manifest.json').read_text())
        cls.runtime = json.loads((builder.RUNTIME / 'manifest.json').read_text())

    def test_verified_release_and_complete_consumed_closure(self):
        self.assertTrue(self.runtime['signature_verified'])
        self.assertEqual(self.runtime['target_compile_units'], 420)
        self.assertEqual(self.runtime['native_tests_count'], 7)
        self.assertTrue(self.runtime['native_tests_passed'])
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for path, digest in self.report[key].items():
                self.assertEqual(builder.sha(Path(path)), digest, path)
        for path in self.report['actual_provider_headers']:
            self.assertNotIn('openssl@3', path)

    def test_original_packet_with_genuine_static_native_crypto(self):
        executable = self.package / 'sshpacketprobe-libressl-host'
        result = subprocess.run([executable], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['native_packet_stdout'])
        self.assertEqual(self.report['valid_packet_cases'], 48)
        self.assertEqual(self.report['rejected_packet_cases'], 5036)
        dynamic = subprocess.check_output(['xcrun', 'otool', '-L', executable], text=True)
        self.assertNotIn('libcrypto.', dynamic)
        self.assertNotIn('libssl.', dynamic)

    def test_real_target_evp_provider_definitions_and_matching_abi(self):
        symbols = subprocess.check_output(['xcrun', 'nm', '-g', self.runtime['target_archive']], text=True)
        for name in ('_EVP_CIPHER_CTX_free', '_EVP_CIPHER_CTX_iv_length', '_EVP_CIPHER_CTX_new',
                     '_EVP_Cipher', '_EVP_CipherInit', '_EVP_chacha20'):
            self.assertRegex(symbols, r'(?m)^[0-9a-f]+ T ' + name + '$')
        imports = subprocess.check_output(['xcrun', 'nm', '-u',
            self.package / 'cipher-chachapoly-libcrypto-target.o'], text=True)
        self.assertIn('_EVP_CIPHER_CTX_iv_length', imports)
        self.assertNotIn('_EVP_CIPHER_CTX_get_iv_length', imports)

    def test_target_platform_gaps_are_preserved_not_stubbed(self):
        self.assertFalse(self.report['target_link_complete'])
        self.assertEqual(self.report['target_missing_symbols'], ['_pthread_equal',
            '_pthread_mutex_lock', '_pthread_mutex_unlock', '_pthread_self', '_sysctlbyname'])
        self.assertIsNone(self.report['actual_static_executable'])
        for key in ('evp_provider_shim', 'entropy_qualified', 'ssh_transport', 'installed', 'pi_executed'):
            self.assertFalse(self.report[key])
        self.assertTrue(self.report['original_apple_config_unchanged'])
        self.assertTrue(self.report['original_apple_packet_source_unchanged'])


if __name__ == '__main__': unittest.main()
