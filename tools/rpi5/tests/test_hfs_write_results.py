# SPDX-License-Identifier: BSD-2-Clause
"""Native temporary regular-file vectors, not a mounted HFS/durability test."""
import os
from pathlib import Path
import tempfile
import unittest

from tools.rpi5 import hfs_write_results as results


class HFSWriteResultsTests(unittest.TestCase):
    def fixture(self,root):
        for name,length,seed in results.VECTORS:
            (root/name).write_bytes(results.payload(length,seed))

    def test_all_five_exact_complete_file_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); self.fixture(root)
            entries=results.verify_files(root)
            self.assertEqual(entries,results.expected_entries())
            self.assertEqual([row['bytes'] for row in entries],[32,0,33034,257,4633])
            self.assertEqual(entries[1]['sha256'],'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')

    def test_changed_truncated_extended_symlink_or_linked_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for fault in ('changed','truncated','extended','symlink','hardlink'):
                self.fixture(root); file=root/results.VECTORS[0][0]
                if fault=='changed': file.write_bytes(b'x'*32)
                if fault=='truncated': file.write_bytes(file.read_bytes()[:-1])
                if fault=='extended': file.write_bytes(file.read_bytes()+b'x')
                if fault=='symlink':
                    file.unlink(); file.symlink_to(root/results.VECTORS[2][0])
                if fault=='hardlink': os.link(file,root/'alias')
                with self.subTest(fault=fault), self.assertRaises((ValueError,OSError)):
                    results.verify_files(root)
                file.unlink()
                if fault=='hardlink': (root/'alias').unlink()


if __name__=='__main__': unittest.main()
