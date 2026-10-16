# SPDX-License-Identifier: BSD-2-Clause
"""Native regular-file install faults; not FAT or hardware acceptance."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import probe_install_core as core


class ProbeInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.boot = self.base / 'boot'; self.boot.mkdir()
        self.old = b'preserved tested SD image\n' * 17
        self.new = b'distinct HFS candidate\n' * 19
        (self.boot / 'probe.bin').write_bytes(self.old)
        (self.boot / 'config.txt').write_bytes(b'unchanged boot configuration')
        candidate = self.base / 'candidate'; candidate.write_bytes(self.new)
        self.directory = os.open(self.boot, os.O_RDONLY | os.O_DIRECTORY)
        self.candidate = os.open(candidate, os.O_RDONLY)
        self.addCleanup(os.close, self.directory)
        self.addCleanup(os.close, self.candidate)
        self.old_hash = hashlib.sha256(self.old).hexdigest()
        self.new_hash = hashlib.sha256(self.new).hexdigest()

    def install(self):
        return core.install(self.directory, self.candidate, self.old_hash, self.new_hash)

    def test_publish_preserves_old_image_and_other_files(self):
        result = self.install()
        self.assertEqual((self.boot / 'probe.bin').read_bytes(), self.new)
        self.assertEqual((self.boot / result['sd_backup']).read_bytes(), self.old)
        self.assertEqual((self.boot / 'config.txt').read_bytes(), b'unchanged boot configuration')
        self.assertFalse((self.boot / 'probe.hfs-read-20261012.tmp').exists())
        self.assertFalse(result['power_loss_atomicity_claimed'])

    def test_correction_uses_distinct_fixed_names_and_preserves_original_backup(self):
        passed = self.boot / 'probe.sd-read-passed-20261012.bin'
        passed.write_bytes(b'earlier passed SD image')
        result = core.install(self.directory, self.candidate, self.old_hash, self.new_hash,
                              'statfs-correction')
        self.assertEqual(passed.read_bytes(), b'earlier passed SD image')
        self.assertEqual(result['sd_backup'], 'probe.hfs-statfs-failed-20261012.bin')
        self.assertEqual((self.boot / result['sd_backup']).read_bytes(), self.old)
        with self.assertRaises(ValueError):
            core.install(self.directory, self.candidate, self.old_hash, self.new_hash, '../arbitrary')

    def test_correction_existing_partial_files_fail_closed(self):
        for name in core.INSTALL_NAMES['statfs-correction']:
            path = self.boot / name
            path.symlink_to(self.base / 'missing')
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.install(self.directory, self.candidate, self.old_hash, self.new_hash, 'statfs-correction')
            self.assertTrue(path.is_symlink())
            path.unlink()
        self.assertEqual((self.boot / 'probe.bin').read_bytes(), self.old)

    def test_cache_diagnostic_keeps_both_older_failed_and_readonly_backups(self):
        names=('probe.hfs-write-no-admission-20261012.bin','probe.hfs-read-passed-20261012.bin')
        for name in names: (self.boot/name).write_bytes(name.encode())
        result=core.install(self.directory,self.candidate,self.old_hash,self.new_hash,'write-cache-diagnostic')
        self.assertEqual(result['sd_backup'],'probe.hfs-write-cache-probe-failed-20261012.bin')
        self.assertEqual((self.boot/result['sd_backup']).read_bytes(),self.old)
        self.assertEqual((self.boot/'probe.bin').read_bytes(),self.new)
        for name in names: self.assertEqual((self.boot/name).read_bytes(),name.encode())

    def test_changed_source_current_or_hash_rejects_before_backup(self):
        for old_hash, new_hash in (('0'*64, self.new_hash), (self.old_hash, '0'*64),
                                    (self.old_hash, self.old_hash), ('bad', self.new_hash)):
            with self.subTest(old_hash=old_hash), self.assertRaises(ValueError):
                core.install(self.directory, self.candidate, old_hash, new_hash)
        self.assertEqual(sorted(path.name for path in self.boot.iterdir()), ['config.txt', 'probe.bin'])

    def test_existing_partial_backup_temp_or_symlink_is_never_overwritten(self):
        for name in ('probe.sd-read-passed-20261012.bin', 'probe.hfs-read-20261012.tmp'):
            path = self.boot / name
            path.symlink_to(self.base / 'missing')
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.install()
            self.assertTrue(path.is_symlink())
            path.unlink()
        self.assertEqual((self.boot / 'probe.bin').read_bytes(), self.old)

    def test_symlink_or_linked_current_image_is_rejected(self):
        current = self.boot / 'probe.bin'
        current.unlink(); current.symlink_to(self.base / 'candidate')
        with self.assertRaises(OSError):
            self.install()
        current.unlink(); current.write_bytes(self.old)
        os.link(current, self.boot / 'alias')
        with self.assertRaises(ValueError):
            self.install()

    def test_short_write_or_interruption_is_bounded_and_original_remains(self):
        for error in (0, InterruptedError()):
            with patch.object(core.os, 'pwrite', side_effect=error if isinstance(error, Exception) else None,
                              return_value=error) as write, self.assertRaises(RuntimeError):
                self.install()
            self.assertLessEqual(write.call_count, 16)
            self.assertEqual((self.boot / 'probe.bin').read_bytes(), self.old)
            (self.boot / 'probe.sd-read-passed-20261012.bin').unlink()

    def test_failed_candidate_readback_retains_backup_and_temp_without_publication(self):
        original = core.copy_image
        def fault(source, directory, name, expected):
            original(source, directory, name, expected)
            if name.endswith('.tmp'):
                raise RuntimeError('candidate readback fault')
        with patch.object(core, 'copy_image', side_effect=fault), self.assertRaises(RuntimeError):
            self.install()
        self.assertEqual((self.boot / 'probe.bin').read_bytes(), self.old)
        self.assertEqual((self.boot / 'probe.sd-read-passed-20261012.bin').read_bytes(), self.old)
        self.assertTrue((self.boot / 'probe.hfs-read-20261012.tmp').exists())


if __name__ == '__main__':
    unittest.main()
