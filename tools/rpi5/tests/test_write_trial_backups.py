# SPDX-License-Identifier: BSD-2-Clause
"""Real regular-file backup I/O with explicitly modeled block-device metadata."""
import contextlib
import hashlib
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import write_trial_backups as runner


class WriteBackupsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = bytes(range(256))*2
        self.source = self.root/'source'; self.source.write_bytes(self.data)
        self.directory = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close, self.directory)

    @contextlib.contextmanager
    def block_model(self, size=128177930240, regular=False):
        original_open, original_stat, original_fstat = os.open, os.stat, os.fstat
        device_fds = set()
        def open_model(path, flags, *args, **kwargs):
            if str(path).startswith('/dev/'):
                self.assertEqual(str(path), '/dev/mmcblk0')
                self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
                self.assertTrue(flags & os.O_NOFOLLOW)
                fd = original_open(self.source, flags, *args, **kwargs)
                device_fds.add(fd)
                return fd
            return original_open(path, flags, *args, **kwargs)
        def fstat_model(fd):
            if fd in device_fds:
                return SimpleNamespace(st_mode=stat.S_IFREG if regular else stat.S_IFBLK, st_rdev=179)
            return original_fstat(fd)
        def stat_model(path, *args, **kwargs):
            return SimpleNamespace(st_rdev=179) if str(path)=='/dev/mmcblk0' else original_stat(path,*args,**kwargs)
        with patch.object(runner.os,'open',side_effect=open_model), \
                patch.object(runner.os,'fstat',side_effect=fstat_model), \
                patch.object(runner.os,'stat',side_effect=stat_model), \
                patch.object(runner.fcntl,'ioctl',return_value=struct.pack('=Q',size)):
            yield

    def snapshot(self, save=True):
        return runner.block_snapshot('/dev/mmcblk0',128177930240,512,
            self.directory if save else None,'mbr.before-write.bin' if save else None)

    def test_complete_file_backup_fsync_and_readback_never_write_sd(self):
        with self.block_model(), patch.object(runner.os,'fsync',wraps=os.fsync) as sync:
            result=self.snapshot()
        self.assertEqual(result,dict(device='/dev/mmcblk0',bytes=512,
            sha256=hashlib.sha256(self.data).hexdigest(),saved_as='mbr.before-write.bin'))
        self.assertEqual((self.root/'mbr.before-write.bin').read_bytes(),self.data)
        self.assertEqual(sync.call_count,2)

    def test_read_only_hash_does_not_create_a_backup(self):
        with self.block_model(): result=self.snapshot(False)
        self.assertIsNone(result['saved_as'])
        self.assertFalse((self.root/'mbr.before-write.bin').exists())

    def test_wrong_device_extent_destination_or_descriptor_is_rejected(self):
        for args in (('/dev/nvme0n1p2',128177930240,512),('/dev/mmcblk0',128177930240,513),
                     ('/dev/mmcblk0',512,512),('/dev/mmcblk0',128177930240,512,self.directory,'hfs-partition.before.img'),
                     ('/dev/mmcblk0',128177930240,512,self.directory,'../escape')):
            with self.subTest(args=args),patch.object(runner.os,'open') as opened,self.assertRaises(ValueError):
                runner.block_snapshot(*args)
            opened.assert_not_called()
        for settings in (dict(size=512),dict(regular=True)):
            with self.subTest(settings=settings),self.block_model(**settings),self.assertRaises(ValueError):
                self.snapshot()

    def test_exclusive_backup_refuses_existing_files_and_symlinks(self):
        target=self.root/'mbr.before-write.bin'; target.write_bytes(b'preserve')
        with self.block_model(),self.assertRaises(FileExistsError): self.snapshot()
        self.assertEqual(target.read_bytes(),b'preserve')
        target.unlink(); target.symlink_to(self.source)
        with self.block_model(),self.assertRaises(FileExistsError): self.snapshot()
        self.assertEqual(self.source.read_bytes(),self.data)

    def test_short_reads_and_destination_stalls_fail_without_success(self):
        for fault in ('read','zero','negative','oversized','stalled','fsync','readback'):
            target=self.root/'mbr.before-write.bin'
            if target.exists(): target.unlink()
            with self.subTest(fault=fault),self.block_model(),contextlib.ExitStack() as stack:
                if fault=='read': stack.enter_context(patch.object(runner.os,'pread',return_value=b'x'))
                if fault in ('zero','negative','oversized'):
                    stack.enter_context(patch.object(runner.os,'pwrite',return_value={'zero':0,'negative':-1,'oversized':513}[fault]))
                if fault=='stalled': stack.enter_context(patch.object(runner.os,'pwrite',side_effect=InterruptedError))
                if fault=='fsync': stack.enter_context(patch.object(runner.os,'fsync',side_effect=OSError('fsync failed')))
                if fault=='readback': stack.enter_context(patch.object(runner.os,'pread',side_effect=[self.data,b'z'*512]))
                with self.assertRaises((RuntimeError,OSError)): self.snapshot()

    def test_partial_destination_writes_are_bounded_and_verified(self):
        original=os.pwrite
        def partial(fd,data,offset): return original(fd,data[:64],offset)
        with self.block_model(),patch.object(runner.os,'pwrite',side_effect=partial) as writes:
            self.snapshot()
        self.assertEqual(writes.call_count,8)
        self.assertEqual((self.root/'mbr.before-write.bin').read_bytes(),self.data)


if __name__=='__main__': unittest.main()
