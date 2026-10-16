# SPDX-License-Identifier: BSD-2-Clause
"""Git-selected source fingerprints; no build or unrelated workspace mutation."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import rpi5


class SourceStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_regular_bytes_remain_exact_hash_bound(self):
        path=self.root/'source.c'; path.write_bytes(b'int source;\n')
        self.assertEqual(rpi5.source_entry_digest(path),hashlib.sha256(path.read_bytes()).hexdigest())
        before=rpi5.source_entry_digest(path); path.write_bytes(b'int changed;\n')
        self.assertNotEqual(before,rpi5.source_entry_digest(path))

    def test_directory_dangling_and_file_links_are_fingerprinted_not_followed(self):
        directory=self.root/'directory'; directory.mkdir()
        file=self.root/'file'; file.write_bytes(b'data')
        for name,target in (('dirlink','directory'),('filelink','file'),('dangling','missing')):
            path=self.root/name; path.symlink_to(target)
            self.assertEqual(rpi5.source_entry_digest(path),hashlib.sha256(b'SYMLINK\0'+os.fsencode(target)).hexdigest())
            with patch.object(rpi5,'digest',side_effect=AssertionError('Must not traverse link')):
                rpi5.source_entry_digest(path)
            before=rpi5.source_entry_digest(path); path.unlink(); path.symlink_to(target+'-other')
            self.assertNotEqual(before,rpi5.source_entry_digest(path))

    def test_every_git_selected_path_and_link_stays_in_strict_before_after_state(self):
        (self.root/'source').write_bytes(b'bytes'); (self.root/'directory').mkdir()
        (self.root/'link').symlink_to('directory')
        with patch.object(rpi5,'ROOT',self.root),patch.object(rpi5.subprocess,'run'), \
                patch.object(rpi5.subprocess,'check_output',side_effect=lambda args,**kw: b'patch' if args[1]=='diff' else b'source\0link\0'), \
                patch.object(rpi5,'capture',side_effect=lambda *args:'HEAD' if args[1]=='rev-parse' else '?? source\n?? link'):
            before=rpi5.source_state({'xnu':{'commit':'baseline'}})
            self.assertEqual(set(before['untracked_sha256']),{'source','link'})
            self.assertEqual(before,rpi5.source_state({'xnu':{'commit':'baseline'}}))
            (self.root/'link').unlink(); (self.root/'link').symlink_to('changed')
            self.assertNotEqual(before,rpi5.source_state({'xnu':{'commit':'baseline'}}))

    def test_unexpected_real_directory_or_missing_entry_still_refuses(self):
        path=self.root/'directory'; path.mkdir()
        with self.assertRaises(IsADirectoryError): rpi5.source_entry_digest(path)
        with self.assertRaises(FileNotFoundError): rpi5.source_entry_digest(self.root/'missing')


if __name__=='__main__': unittest.main()
