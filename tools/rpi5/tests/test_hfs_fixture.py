# SPDX-License-Identifier: BSD-2-Clause
"""Pure fixture-header/virtual-device guards; no real images mounted by tests."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

from tools.rpi5.prepare_hfs_fixture import IMAGE_BYTES, inspect_header, inspect_image, own_attachment, attachment_device


def header(free=100):
    data = bytearray(512)
    struct.pack_into('>HHI', data, 0, 0x482b, 4, 0x80000100)
    struct.pack_into('>III', data, 40, 4096, IMAGE_BYTES // 4096, free)
    return data


class HFSFixtureTests(unittest.TestCase):
    def test_clean_raw_header_geometry(self):
        report = inspect_header(header(), IMAGE_BYTES)
        self.assertEqual(report['signature'], 'H+')
        self.assertEqual(report['block_size'] * report['total_blocks'], IMAGE_BYTES)

    def test_dirty_journaled_protected_and_bad_geometry_rejected(self):
        for offset, kind, value in ((0, 'H', 0), (2, 'H', 5), (4, 'I', 0),
                                    (4, 'I', 0x2100), (4, 'I', 0x4100), (4, 'I', 0x40000100),
                                    (40, 'I', 511), (40, 'I', 768), (44, 'I', 1),
                                    (48, 'I', IMAGE_BYTES // 4096 + 1)):
            with self.subTest(offset=offset, value=value):
                data = header(); struct.pack_into('>' + kind, data, offset, value)
                with self.assertRaises(ValueError): inspect_header(data, IMAGE_BYTES)
        with self.assertRaises(ValueError): inspect_header(header()[:-1], IMAGE_BYTES)
        with self.assertRaises(ValueError): inspect_header(header(), IMAGE_BYTES + 512)

    def test_backup_counter_can_be_stale_but_geometry_and_clean_state_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'synthetic.raw'
            with image.open('xb') as output:
                output.truncate(IMAGE_BYTES)
                output.seek(1024); output.write(header(100))
                output.seek(IMAGE_BYTES - 1024); output.write(header(101))
            report = inspect_image(image)
            self.assertEqual(report['free_blocks'], 100)
            self.assertEqual(report['alternate_free_blocks'], 101)
            with image.open('r+b') as output:
                data = header(); struct.pack_into('>I', data, 4, 0x2100)
                output.seek(IMAGE_BYTES - 1024); output.write(data)
            with self.assertRaises(ValueError): inspect_image(image)
            link = Path(directory) / 'alias.raw'; link.symlink_to(image)
            with self.assertRaises(ValueError): inspect_image(link)

    def info(self, image, mountpoint=None):
        entity = {'dev-entry': '/dev/disk123', 'content-hint': ''}
        if mountpoint is not None: entity['mount-point'] = str(mountpoint)
        return {'images': [{'image-path': str(image), 'writeable': False,
                            'blocksize': 512, 'blockcount': IMAGE_BYTES // 512,
                            'image-encrypted': False, 'system-entities': [entity]}]}

    def test_exact_readonly_virtual_attachment_with_and_without_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            image, mountpoint = Path(directory) / 'image.cdr', Path(directory) / 'mount'
            for mounted in (None, mountpoint):
                info = self.info(image, mounted)
                self.assertEqual(own_attachment(info, image, mounted), '/dev/disk123')
                self.assertEqual(attachment_device(info, image), '/dev/disk123')
            with self.assertRaises(ValueError): own_attachment(self.info(image, mountpoint), image)
            with self.assertRaises(ValueError): own_attachment(self.info(image), image, mountpoint)

    def test_ambiguous_unrelated_writable_or_partition_device_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image, mountpoint = Path(directory) / 'image.cdr', Path(directory) / 'mount'
            base = self.info(image, mountpoint)
            for fault in ('missing', 'duplicate', 'writable', 'geometry', 'encrypted',
                          'partition', 'extra-device', 'content', 'mountpoint'):
                with self.subTest(fault=fault):
                    info = copy.deepcopy(base); row = info['images'][0]
                    if fault == 'missing': row['image-path'] = '/unrelated.cdr'
                    if fault == 'duplicate': info['images'].append(copy.deepcopy(row))
                    if fault == 'writable': row['writeable'] = True
                    if fault == 'geometry': row['blockcount'] += 1
                    if fault == 'encrypted': row['image-encrypted'] = True
                    if fault == 'partition': row['system-entities'][0]['dev-entry'] += 's1'
                    if fault == 'extra-device': row['system-entities'].append(copy.deepcopy(row['system-entities'][0]))
                    if fault == 'content': row['system-entities'][0]['content-hint'] = 'Apple_APFS'
                    if fault == 'mountpoint': row['system-entities'][0]['mount-point'] = '/elsewhere'
                    with self.assertRaises(ValueError): own_attachment(info, image, mountpoint)
                    if fault in ('missing', 'duplicate', 'partition', 'extra-device'):
                        with self.assertRaises(ValueError): attachment_device(info, image)
