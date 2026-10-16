# SPDX-License-Identifier: BSD-2-Clause
"""Future writable-mount utility: explicit syscall doubles, no real mounts."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HFS = ROOT / 'build/rpi5/gate4-sources/hfs/hfs-hfs-715.120.4/core'
SOURCE = ROOT / 'tools/rpi5/user/hfsrw.c'


class HFSRWMountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (HFS / 'hfs_mount.h').is_file():
            raise unittest.SkipTest('Pinned Apple HFS sources are not prepared')
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / 'hfsrw'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DRPI5_HFS_WRITE_TRIAL=1', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-I', str(HFS),
                        str(ROOT / 'tools/rpi5/tests/hfsrw_host.c'), str(SOURCE),
                        '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_trial(self, *args, mode=''):
        result = subprocess.run([str(self.binary), *args], capture_output=True, timeout=10,
                                env={**os.environ, 'HFSRW_FIXTURE': mode})
        self.assertNotIn(b'Sanitizer', result.stderr)
        return result

    def test_exact_mount_status_and_normal_unmount_markers(self):
        for op, counts in (
                ('mount', b'STATS=2 OPENS=1 CLOSES=1 IOCTLS=3 MOUNTS=1 UNMOUNTS=0'),
                ('status', b'STATS=1 OPENS=1 CLOSES=1 IOCTLS=3 MOUNTS=0 UNMOUNTS=0'),
                ('unmount', b'STATS=2 OPENS=1 CLOSES=1 IOCTLS=3 MOUNTS=0 UNMOUNTS=1')):
            result = self.run_trial(op)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b'RPI5XNU:HFSRW:' + op.upper().encode().replace(b'MOUNT', b'MOUNTED')
                             + b' DEVICE=/dev/disk0s2 PATH=/mnt/hfs READONLY=0 DURABILITY_VERIFIED=0\n')
            self.assertIn(counts, result.stderr)

    def test_invalid_arguments_make_no_syscalls(self):
        for args in ((), ('rw',), ('mount', '/dev/disk0s2'), ('unmount', 'force'), ('mount', '/elsewhere')):
            result = self.run_trial(*args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(b'STATS=0 OPENS=0 CLOSES=0 IOCTLS=0 MOUNTS=0 UNMOUNTS=0', result.stderr)

    def test_pre_mount_identity_and_geometry_fail_before_mount(self):
        for mode in ('stat', 'type', 'target', 'root-writable', 'already-mounted', 'unterminated',
                     'open', 'close', 'ioctl', 'count-ioctl', 'writable-ioctl', 'blocksize',
                     'capacity', 'protected', 'malformed-writable'):
            result = self.run_trial('mount', mode=mode)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'MOUNTS=0 UNMOUNTS=0', result.stderr)

    def test_failed_or_wrong_mount_result_emits_no_marker(self):
        for mode in ('mount', 'interrupt', 'poststat', 'from', 'readonly', 'noexec', 'flags'):
            result = self.run_trial('mount', mode=mode)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'MOUNTS=1 UNMOUNTS=0', result.stderr)

    def test_unmount_checks_current_admission_and_never_forces_or_masks_sync_error(self):
        for mode in ('stat', 'type', 'target', 'from', 'readonly', 'noexec', 'flags', 'unterminated',
                     'not-mounted', 'open', 'close', 'ioctl', 'protected', 'malformed-writable',
                     'sync-failure', 'busy', 'poststat', 'unmount-still-mounted', 'root-writable'):
            result = self.run_trial('unmount', mode=mode)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, b'')
            attempted = mode in ('sync-failure', 'busy', 'poststat', 'unmount-still-mounted', 'root-writable')
            self.assertIn(b'UNMOUNTS=' + (b'1' if attempted else b'0'), result.stderr)

    def test_status_rechecks_writable_device_and_exact_mount(self):
        for mode in ('from', 'readonly', 'noexec', 'flags', 'protected', 'ioctl', 'close'):
            result = self.run_trial('status', mode=mode)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'MOUNTS=0 UNMOUNTS=0', result.stderr)

    def test_compile_time_gate_and_real_darwin_abi(self):
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
        for enabled in (False, True):
            obj = Path(self.tmp.name) / ('hfsrw-on.o' if enabled else 'hfsrw-off.o')
            command = ['xcrun', 'clang', '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-c', '-Os',
                       '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-Wall', '-Wextra', '-Werror']
            if enabled:
                command += ['-DRPI5_HFS_WRITE_TRIAL=1', '-I', str(HFS)]
            subprocess.run([*command, str(SOURCE), '-o', str(obj)], check=True)
            symbols = set(subprocess.check_output(['xcrun', 'nm', '-ju', str(obj)], text=True).splitlines())
            self.assertEqual(symbols, {'_rt_call', '_rt_open', '_rt_close', '_rt_equal', '_rt_error', '_rt_put'}
                             if enabled else set())
            definitions = subprocess.check_output(['xcrun', 'nm', '-jU', str(obj)], text=True).splitlines()
            self.assertEqual('_hfsrw_main' in definitions, enabled)


if __name__ == '__main__':
    unittest.main()
