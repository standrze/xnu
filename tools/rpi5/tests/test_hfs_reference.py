# SPDX-License-Identifier: BSD-2-Clause
"""Mock Linux two-partition capture faults; not physical storage evidence."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.rpi5 import capture_hfs_reference as capture


def baseline():
    sectors = 250347520
    return {'identity': {
        'root': '/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c',
        'bytes': sectors * 512,
        'layout': dict(label='dos', id='0x5ae1f07e', device='/dev/mmcblk0', unit='sectors',
                       sectorsize=512, partitions=[dict(node='/dev/mmcblk0p1', start=2048,
                                                        size=1048576, type='c', bootable=True)]),
        'partition': dict(TYPE='vfat', LABEL='XNU_PROBE', UUID='4FA7-3725', PARTUUID='5ae1f07e-01'),
        'card': dict(type='SD', cid='1b534d474432533530654f68d1a16100',
                     csd='400e0032db790003baff7f800a400000')}, 'sd_write_operations': 0,
        'sectors': [dict(lba=n, bytes=512, reads=2, sha256='0' * 64)
                    for n in (0, 1, 2047, 2048, 1050623, 1050624, sectors // 2, sectors - 1)]}


class HFSReferenceTests(unittest.TestCase):
    def run_remote(self, fault=None):
        expected = capture.expected_identity(baseline())
        changed = copy.deepcopy(expected)
        if fault == 'root':
            changed['root'] = '/dev/mmcblk0p2 ext4 OTHER'
        if fault == 'layout':
            changed['layout']['partitions'][0]['size'] -= 1
        if fault == 'partition':
            changed['hfs_partition']['PARTUUID'] = 'OTHER'
        block = b'\xa5' * (1024 * 1024)
        image_hash = hashlib.sha256(block * 128).hexdigest()
        reads, cid_reads = 0, 0

        def command(args, **kwargs):
            if args[0] == 'findmnt':
                return changed['root']
            if args[0] == 'sfdisk':
                return json.dumps({'partitiontable': changed['layout']})
            self.assertEqual(args[:3], ('blkid', '-o', 'export'))
            name = 'boot_partition' if args[3] == '/dev/mmcblk0p1' else 'hfs_partition'
            return '\n'.join(f'{key}={value}' for key, value in changed[name].items())

        def read_text(path):
            nonlocal cid_reads
            if path == Path('/sys/block/mmcblk0/size'):
                return str(expected['bytes'] // 512)
            if path == Path('/sys/class/block/mmcblk0p2/start'):
                return str(expected['partition_start'])
            if path == Path('/sys/class/block/mmcblk0p2/size'):
                return str(expected['partition_sectors'])
            self.assertEqual(path.parent, Path('/sys/block/mmcblk0/device'))
            if path.name == 'cid':
                cid_reads += 1
                if fault == 'changed' and cid_reads == 2:
                    return '0' * 32
            return expected['card'][path.name]

        def pread(fd, length, offset):
            nonlocal reads
            self.assertEqual((fd, length, offset), (9, len(block), (reads % 128) * len(block)))
            reads += 1
            if fault == 'short':
                return block[:-1]
            if fault == 'unstable' and reads > 128:
                return b'\x5a' * len(block)
            return block

        output = io.StringIO()
        size = capture.IMAGE_BYTES - (512 if fault == 'capacity' else 0)
        with (patch('subprocess.check_output', side_effect=command),
              patch('subprocess.run', return_value=SimpleNamespace(returncode=0 if fault == 'mounted' else 1,
                                                                   stdout='')),
              patch('pathlib.Path.read_text', autospec=True, side_effect=read_text),
              patch('os.open', return_value=9) as opened,
              patch('os.close') as closed,
              patch('os.fstat', return_value=SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=179)),
              patch('os.stat', return_value=SimpleNamespace(st_rdev=180 if fault == 'descriptor' else 179)),
              patch('os.pread', side_effect=pread),
              patch('fcntl.ioctl', return_value=struct.pack('=Q', size)),
              contextlib.redirect_stdout(output)):
            self.opened, self.closed = opened, closed
            exec(compile(capture.remote_source(expected, image_hash), '<readonly-hfs-capture>', 'exec'), {})
        self.reads = reads
        return json.loads(output.getvalue()), {'image_sha256': image_hash}

    def test_two_complete_passes_exact_readonly_descriptor_and_hash(self):
        report, fixture = self.run_remote()
        capture.validate_capture(report, baseline(), fixture)
        self.assertEqual(self.reads, 256)
        path, flags = self.opened.call_args.args
        self.assertEqual(path, '/dev/mmcblk0p2')
        self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
        self.assertTrue(flags & os.O_NOFOLLOW)
        self.closed.assert_called_once_with(9)

    def test_wrong_root_layout_partition_or_mount_rejected_before_open(self):
        for fault in ('root', 'layout', 'partition', 'mounted'):
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                self.run_remote(fault)
            self.opened.assert_not_called()
            self.closed.assert_not_called()

    def test_short_changed_capacity_descriptor_or_unstable_data_balances_close(self):
        for fault in ('short', 'changed', 'capacity', 'descriptor', 'unstable'):
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                self.run_remote(fault)
            self.closed.assert_called_once_with(9)

    def test_capture_tamper_or_incomplete_coverage_fails(self):
        report, fixture = self.run_remote()
        variants = []
        for path, value in ((('identity', 'bytes'), 1), (('sd_write_operations',), 1),
                            (('sd_write_operations',), False),
                            (('partition_reads',), report['partition_reads'][:1])):
            bad = copy.deepcopy(report)
            parent = bad
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            variants.append(bad)
        for field, value in (('bytes', 512), ('sha256', '0' * 64),
                             ('pass_number', 2), ('pass_number', True)):
            bad = copy.deepcopy(report)
            bad['partition_reads'][0][field] = value
            variants.append(bad)
        for bad in variants:
            with self.subTest(report=bad), self.assertRaises(ValueError):
                capture.validate_capture(bad, baseline(), fixture)

    def test_initial_one_partition_reference_is_not_weakened(self):
        bad = baseline()
        bad['identity']['layout'] = capture.expected_identity(bad)['layout']
        with self.assertRaises(ValueError):
            capture.expected_identity(bad)

    def test_fixture_guards_require_raw_hash_headers_files_and_mac_checks(self):
        fixture = dict(image='/not-opened-test-image', image_bytes=capture.IMAGE_BYTES,
                       image_sectors=capture.PARTITION_SECTORS, image_sha256='0' * 64,
                       volume_name=capture.VOLUME, volume_header={'test': 'header'},
                       mac_readonly_mount_verified=True, readonly_fsck_verified=True,
                       mac_attachment_detached=True, pi_sd_changes=0,
                       files=[dict(path=path, bytes=0, sha256='0' * 64,
                                   mode=0o555 if path == '/bin/echo' else 0o444)
                              for path in capture.FILE_PATHS])
        with patch.object(capture, 'inspect_image', return_value={'test': 'header'}), \
                patch.object(capture, 'digest', return_value='0' * 64):
            capture.validate_fixture(fixture)
            for changed in ({**fixture, 'image_sha256': '1' * 64},
                            {**fixture, 'volume_header': {}},
                            {**fixture, 'readonly_fsck_verified': False},
                            {**fixture, 'pi_sd_changes': False},
                            {**fixture, 'files': fixture['files'][:-1]},
                            {**fixture, 'files': [fixture['files'][0]] * 5}):
                with self.subTest(fixture=changed), self.assertRaises(ValueError):
                    capture.validate_fixture(changed)


if __name__ == '__main__':
    unittest.main()
