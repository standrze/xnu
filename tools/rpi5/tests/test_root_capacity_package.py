# SPDX-License-Identifier: BSD-2-Clause
"""Actual expanded files/catalogue on native Darwin; synthetic mount and syscalls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import root_capacity_profile as profile
from tools.rpi5 import prepare_socket_identity_root as identity
from tools.rpi5 import socket_identity_evidence as evidence


class ExpandedPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ.get('RPI5_CAPACITY_ROOT', str(profile.ROOT / 'build/rpi5/root-capacity-ssh-20261013-b')))
        cls.report = json.loads((cls.package / 'manifest.json').read_text())
        cls.raw = (cls.package / 'ramdisk.bin').read_bytes()
        if profile.sha(cls.raw) != cls.report['output_sha256']:
            raise ValueError('Actual expanded package changed')
        cls.files = profile.files_from(cls.raw)
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.tree = cls.base / 'tree'
        directories = []
        for row in profile.inspect(cls.raw)['entries']:
            path = cls.tree / row['path'].lstrip('/')
            if row['type'] == 'directory':
                path.mkdir(parents=True, exist_ok=True)
                directories.append(path)
            else:
                path.write_bytes(cls.files[row['path']][0])
                path.chmod(row['mode'])
        for path in directories:
            path.chmod(0o555)
        cls.program = cls.base / 'native'
        sources = [identity.old.SOURCE / 'rootidentity.c', Path(__file__).with_name('rootidentity_native.c')]
        sources += [identity.BEARSSL / 'src' / name for name in ('hash/sha2small.c', 'codec/dec32be.c', 'codec/enc32be.c')]
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        '-DIDENTITY_NODES=' + str(cls.report['output_nodes']),
                        '-DIDENTITY_BLOCKS=' + str(len(cls.raw) // 16384),
                        '-I' + str(cls.package), '-I' + str(identity.BEARSSL / 'inc'),
                        '-I' + str(identity.BEARSSL / 'src'), *map(str, sources), '-o', str(cls.program)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        for path in cls.tree.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
        cls.tree.chmod(0o755)
        cls.temp.cleanup()

    def test_actual_complete_expanded_catalogue(self):
        result = subprocess.run([str(self.program), str(self.tree), 'none', '0'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())
        self.assertEqual(result.stderr, b'')
        parsed = evidence.validate(result.stdout, self.report)
        self.assertEqual(parsed['nodes'], 33)
        self.assertEqual(parsed['file_hashes'], 22)
        self.assertRegex(result.stdout, rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')
        self.assertEqual(profile.sha(self.files['/usr/local/libexec/xnu/sshbufferprobe'][0]),
                         '8b311da88fa7bf19bd7b7d0ad098186f196022afdc7aa2ef6b759d1d4cdbf17e')

    def test_corrupt_file_and_wrong_root_geometry_fail(self):
        for scenario in ('payload', 'statfs-nodes'):
            result = subprocess.run([str(self.program), str(self.tree), scenario, '0'], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout.decode() + result.stderr.decode())
            self.assertEqual(result.stderr, b'')
            self.assertIn(b'ROOTIDENTITY:FAIL', result.stdout)
            self.assertRegex(result.stdout, rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')
            with self.assertRaises(ValueError):
                evidence.validate(result.stdout, self.report)


if __name__ == '__main__':
    unittest.main()
