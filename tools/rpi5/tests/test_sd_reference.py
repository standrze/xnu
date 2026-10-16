# SPDX-License-Identifier: BSD-2-Clause
"""Capture tool guards with mocked Linux syscalls; no hardware proof."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.rpi5.capture_sd_reference import REMOTE, validate_capture
from tools.rpi5.capture_linux_tree import REMOTE as TREE_REMOTE


class SDReferenceTests(unittest.TestCase):
    def run_remote(self, *, wrong_root=False, wrong_partition=False, short=False,
                   unstable=False, changed=False):
        size = 128177930240
        self.layout = dict(label='dos', id='0x5ae1f07e', device='/dev/mmcblk0', unit='sectors',
                           sectorsize=512, partitions=[dict(node='/dev/mmcblk0p1', start=2048,
                                                           size=1048576, type='c', bootable=True)])
        self.card = dict(cid='1b534d474432533530654f68d1a16100', csd='400e0032db790003baff7f800a400000',
                         scr='0205848700000000', ocr='0x00300000', name='TEST', type='SD', date='01/2022',
                         manfid='0x1b', oemid='0x534d', serial='0x654f68d1')
        self.cid_reads = 0
        self.pread_count = 0

        def command(args, **kwargs):
            self.assertTrue(kwargs['text'])
            if args[0] == 'findmnt':
                return '/dev/mmcblk0p2 ext4 wrong' if wrong_root else '/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c'
            if args[0] == 'sfdisk':
                return json.dumps(dict(partitiontable=self.layout))
            self.assertEqual(args, ('blkid', '-o', 'export', '/dev/mmcblk0p1'))
            label = 'OTHER' if wrong_partition else 'XNU_PROBE'
            return f'TYPE=vfat\nLABEL={label}\nUUID=4FA7-3725\nPARTUUID=5ae1f07e-01\n'

        def read_text(path, **kwargs):
            if path.name == 'size':
                return str(size // 512)
            self.assertEqual(path.parent, Path('/sys/block/mmcblk0/device'))
            if path.name == 'cid':
                self.cid_reads += 1
                if changed and self.cid_reads == 2:
                    return '0' * 32
            return self.card[path.name]

        def pread(fd, length, offset):
            self.assertEqual((fd, length, offset % 512), (9, 512, 0))
            self.pread_count += 1
            if short:
                return b'\0' * 511
            return bytes([self.pread_count % 2 if unstable else (offset // 512) % 256]) * 512

        output = io.StringIO()
        with (patch('subprocess.check_output', side_effect=command),
              patch('pathlib.Path.read_text', autospec=True, side_effect=read_text),
              patch('pathlib.Path.exists', return_value=False),
              patch('os.open', return_value=9) as opened,
              patch('os.close') as closed,
              patch('os.fstat', return_value=SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=179)),
              patch('os.stat', return_value=SimpleNamespace(st_rdev=179)),
              patch('os.pread', side_effect=pread),
              patch('fcntl.ioctl', return_value=struct.pack('=Q', size)),
              contextlib.redirect_stdout(output)):
            self.opened, self.closed = opened, closed
            exec(compile(REMOTE, '<remote-read-only-capture>', 'exec'), {})
        return json.loads(output.getvalue())

    def test_exact_device_readonly_and_capacity_crosscheck(self):
        report = self.run_remote()
        validate_capture(report)
        name, flags = self.opened.call_args.args
        self.assertEqual(name, '/dev/mmcblk0')
        self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
        self.assertTrue(flags & os.O_NOFOLLOW)
        self.assertEqual(self.pread_count, 16)
        self.closed.assert_called_once_with(9)
        self.assertEqual(report['sectors'][-1]['lba'], 250347519)

    def test_wrong_root_or_partition_rejects_before_open(self):
        for option in ('wrong_root', 'wrong_partition'):
            with self.subTest(option=option), self.assertRaises(RuntimeError):
                self.run_remote(**{option: True})
            self.opened.assert_not_called()
            self.closed.assert_not_called()

    def test_short_unstable_and_card_replacement_reject_and_close(self):
        for option in ('short', 'unstable', 'changed'):
            with self.subTest(option=option), self.assertRaises(RuntimeError):
                self.run_remote(**{option: True})
            self.closed.assert_called_once_with(9)

    def test_report_tamper_rejected(self):
        report = self.run_remote()
        for key, value in (('bytes', 1000000000), ('root', '/dev/mmcblk0p2 ext4 OTHER')):
            bad = copy.deepcopy(report)
            bad['identity'][key] = value
            with self.assertRaises(ValueError):
                validate_capture(bad)
        for key in ('cid', 'csd'):
            bad = copy.deepcopy(report)
            bad['identity']['card'][key] = 'z' * 32
            with self.assertRaises(ValueError):
                validate_capture(bad)
        for field, value in (('reads', 1), ('bytes', 511), ('sha256', 'x' * 64), ('lba', 99)):
            bad = copy.deepcopy(report)
            bad['sectors'][0][field] = value
            with self.assertRaises(ValueError):
                validate_capture(bad)

    def test_storage_tree_filter_is_opt_in_and_excludes_chosen(self):
        # Inspect the actual remote filter, not an independently re-created list.
        import ast
        tree = ast.parse(TREE_REMOTE)
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'storage_capture' for t in n.targets))
        self.assertIs(assignment.value.value, False)
        self.assertIn("if storage_capture: roots+=('sd-vcc-reg','sd-io-1v8-reg')", TREE_REMOTE)
        self.assertNotIn("'chosen'", TREE_REMOTE)
        self.assertNotIn('random-seed', TREE_REMOTE)


if __name__ == '__main__':
    unittest.main()
