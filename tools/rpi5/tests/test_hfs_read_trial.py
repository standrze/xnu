# SPDX-License-Identifier: BSD-2-Clause
"""HFS utility syscall/ABI fixtures; no real host or Pi filesystem access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HFS = ROOT / 'build/rpi5/gate4-sources/hfs/hfs-hfs-715.120.4/core'


class HFSReadTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (HFS / 'hfs_mount.h').is_file():
            raise unittest.SkipTest('Pinned HFS sources are not prepared')
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / 'hfsro'
        result = subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                 '-I', str(HFS), str(ROOT / 'tools/rpi5/tests/hfsro_host.c'),
                                 str(ROOT / 'tools/rpi5/user/hfsro.c'), '-o', str(cls.binary)],
                                capture_output=True)
        if result.returncode:
            cls.tmp.cleanup()
            raise RuntimeError(result.stderr.decode())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, *args, mode=''):
        result = subprocess.run([str(self.binary), *args], capture_output=True, timeout=10,
                                env={**os.environ, 'HFSRO_FIXTURE': mode})
        self.assertNotIn(b'Sanitizer', result.stderr)
        return result

    def test_mount_uses_native_readonly_arguments_and_checks_result(self):
        result = self.run_probe('mount', '/dev/disk0s2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'RPI5XNU:HFSRO:MOUNTED DEVICE=/dev/disk0s2 PATH=/mnt/hfs READONLY=1\n')
        self.assertIn(b'STATS=2 OPENS=1 CLOSES=1 IOCTLS=3 MOUNTS=1 UNMOUNTS=0', result.stderr)

    def test_invalid_options_and_other_partitions_make_no_syscalls(self):
        for args in ((), ('mount',), ('rw', '/dev/disk0s2'), ('mount', '/dev/rdisk0s2'),
                     ('mount', '/dev/disk0s1'), ('mount', '/dev/disk0'), ('mount', '/dev/disk32s2'),
                     ('mount', '/dev/disk00s2'), ('mount', '/dev/disk1s2/../s1'),
                     ('mount', '/dev/disk0s2', '/elsewhere'), ('mount', '')):
            with self.subTest(args=args):
                result = self.run_probe(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'STATS=0 OPENS=0 CLOSES=0 IOCTLS=0 MOUNTS=0 UNMOUNTS=0', result.stderr)

    def test_pre_mount_guards_never_attempt_mount(self):
        for mode in ('stat', 'type', 'already-mounted', 'open', 'ioctl', 'blocksize',
                     'zero-blocks', 'large-blocks', 'writable', 'close'):
            with self.subTest(mode=mode):
                result = self.run_probe('mount', '/dev/disk0s2', mode=mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'MOUNTS=0 UNMOUNTS=0', result.stderr)
                if mode in ('ioctl', 'blocksize', 'zero-blocks', 'large-blocks', 'writable', 'close'):
                    self.assertIn(b'OPENS=1 CLOSES=1', result.stderr)

    def test_mount_failure_or_wrong_result_never_emits_success(self):
        for mode in ('mount', 'interrupt', 'poststat', 'from', 'target', 'flags', 'unterminated'):
            with self.subTest(mode=mode):
                result = self.run_probe('mount', '/dev/disk0s2', mode=mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'MOUNTS=1 UNMOUNTS=0', result.stderr)

    def test_status_and_normal_unmount_do_not_open_the_device(self):
        for operation, marker, counts in (
            ('status', b'STATUS', b'STATS=1 OPENS=0 CLOSES=0 IOCTLS=0 MOUNTS=0 UNMOUNTS=0'),
            ('unmount', b'UNMOUNTED', b'STATS=2 OPENS=0 CLOSES=0 IOCTLS=0 MOUNTS=0 UNMOUNTS=1')):
            result = self.run_probe(operation, '/dev/disk31s2')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b'RPI5XNU:HFSRO:' + marker, result.stdout)
            self.assertIn(counts, result.stderr)

    def test_unmount_requires_exact_readonly_identity_and_success(self):
        for mode in ('stat', 'not-mounted', 'type', 'from', 'target', 'flags', 'unterminated',
                     'unmount', 'poststat', 'unmount-still-mounted'):
            with self.subTest(mode=mode):
                result = self.run_probe('unmount', '/dev/disk0s2', mode=mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'UNMOUNTS=' + (b'1' if mode in ('unmount', 'poststat', 'unmount-still-mounted') else b'0'), result.stderr)
