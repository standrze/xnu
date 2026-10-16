# SPDX-License-Identifier: BSD-2-Clause
"""Complete new root catalogue and actual derived shell logic, never Pi execution."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools.rpi5 import root_capacity_commands as builder
from tools.rpi5 import socket_identity_evidence as evidence
from tools.rpi5.tests.test_root_capacity_package import ExpandedPackageTests as OriginalFixture


class CommandBatchTests(OriginalFixture):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'RPI5_CAPACITY_ROOT': os.environ.get('RPI5_COMMAND_ROOT',
            str(builder.ROOT / 'build/rpi5/root96-command-batch-uc8f3v5l'))}):
            super().setUpClass()
        builder.verify(cls.report['inputs_sha256'])
        builder.verify(cls.report['generated_sha256'])
        cls.shell = cls.base / 'shell-native'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
            '-I', str(builder.SOURCE), str(Path(__file__).with_name('shell_host.c')),
            str(builder.SOURCE / 'parser.c'), str(cls.package / 'shell.c'),
            str(builder.SOURCE / 'utilities.c'), '-o', str(cls.shell)],
            check=True, capture_output=True, timeout=60)

    def test_actual_complete_expanded_catalogue(self):
        result = subprocess.run([str(self.program), str(self.tree), 'none', '0'],
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())
        self.assertEqual(result.stderr, b'')
        parsed = evidence.validate(result.stdout, self.report)
        self.assertEqual(parsed['nodes'], 41)
        self.assertEqual(parsed['file_hashes'], 29)
        self.assertRegex(result.stdout, rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')

    def test_namespace_and_byte_identical_compatibility_entries(self):
        for canonical, old in builder.ALIASES.items():
            self.assertEqual(self.files[canonical], self.files[old])
            self.assertEqual(self.files[canonical][1], 0o555)
        self.assertEqual(builder.profile.sha(self.files['/bin/pwd'][0]),
            '353b4d1889747ec6ed55a6093e1de6eed1315cf4fa3d9bfd06dc34ba53169eb1')
        self.assertEqual(builder.profile.sha(self.files['/usr/local/libexec/xnu/sshcryptoprobe'][0]),
            '1f4a41e8720e37b560fd103b0679f53a4fbee64f481765fcb59d45dddb6ca3c1')
        self.assertNotIn('/bin/date', self.files)
        self.assertEqual(self.files['/etc/paths'],
            (b'/usr/bin\n/bin\n/usr/sbin\n/sbin\n', 0o444))
        for path, value in self.report['unchanged_files_sha256'].items():
            self.assertEqual(builder.profile.sha(self.files[path][0]), value)

    def shell_run(self, command, expected=0):
        result = subprocess.run([str(self.shell), '-c', command], capture_output=True,
            timeout=10, env={'PWD': '/', 'PATH': '/deliberately/not/the/test/path'})
        self.assertEqual(result.returncode, expected, result.stderr.decode())
        self.assertNotIn(b'Sanitizer', result.stderr)
        return result

    def test_actual_shell_uses_canonical_search_and_child_path(self):
        self.assertEqual(self.shell_run('uname -s').stdout, b'Darwin\n')
        self.assertEqual(int(self.shell_run("echo 'hello world' | wc -c").stdout), 12)
        environment = self.shell_run('env').stdout.splitlines()
        self.assertIn(('PATH=' + builder.CANONICAL_PATH).encode(), environment)
        self.assertNotIn(b'PATH=/deliberately/not/the/test/path', environment)
        self.shell_run('rpi5_missing_command_20261013', 127)
        self.assertEqual(self.shell_run('/bin/echo EXPLICIT').stdout, b'EXPLICIT\n')
        self.assertEqual(self.shell_run('false || echo RECOVERED').stdout, b'RECOVERED\n')

    def test_only_expected_recovery_source_sections_changed(self):
        for name in ('init.c', 'shell.c'):
            self.assertEqual((self.package / name).read_text(), builder.derive_recovery(name)[1])
        before = builder.profile.files_from((builder.BASE / 'ramdisk.bin').read_bytes())
        self.assertTrue(builder.replay_equal((self.package / 'recovery-baseline').read_bytes(),
            before['/sbin/launchd'][0]))
        self.assertEqual(self.files['/bin/sh'], self.files['/sbin/launchd'])
        self.assertNotEqual(self.files['/bin/sh'], before['/bin/sh'])
        self.assertEqual(self.files['/bin/zsh'], before['/bin/zsh'])


if __name__ == '__main__':
    unittest.main()
