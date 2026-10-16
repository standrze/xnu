# SPDX-License-Identifier: BSD-2-Clause
"""Linked-byte checker fixtures only; never device or runtime acceptance."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_hfs_stats_package as stats


class HFSStatsPackageTests(unittest.TestCase):
    def bundle(self):
        raw = bytearray(512)
        struct.pack_into('<Q', raw, 40, 0x2000)
        segments = [dict(vmaddr=0x1000, filesize=256, fileoff=0, initprot=3),
                    dict(vmaddr=0x2000, filesize=256, fileoff=256, initprot=5)]
        symbols = '0000000000001000 (__DATA,__data) external _mockfs_vfsops\n' + \
                  '0000000000002000 (__TEXT,__text) non-external _mockfs_vfs_getattr\n'
        return raw, segments, symbols, (stats.ROOT / 'bsd/sys/mount.h').read_text()

    def test_actual_header_getter_offset_excludes_commented_statfs(self):
        raw, segments, symbols, header = self.bundle()
        result = stats.linked_getter(raw, segments, symbols, header)
        self.assertEqual(result['slot_offset'], 40)
        self.assertEqual(result['slot_value'], result['getter_address'])

    def test_wrong_or_missing_pointer_symbols_mapping_or_abi_rejected(self):
        for fault in ('zero-slot', 'wrong-slot', 'missing', 'duplicate', 'short-table',
                      'overlap', 'not-code', 'truncated', 'abi', 'extra-member'):
            raw, segments, symbols, header = self.bundle()
            if fault == 'zero-slot': struct.pack_into('<Q', raw, 40, 0)
            if fault == 'wrong-slot': struct.pack_into('<Q', raw, 40, 0x2004)
            if fault == 'missing': symbols = symbols.splitlines()[0]
            if fault == 'duplicate': symbols += symbols
            if fault == 'short-table': segments[0]['filesize'] = 159
            if fault == 'overlap': segments += [segments[0].copy()]
            if fault == 'not-code': segments[1]['initprot'] = 1
            if fault == 'truncated': raw = raw[:256]
            if fault == 'abi': header = header.replace('(*vfs_getattr)', '(*vfs_other)')
            if fault == 'extra-member': header = header.replace('struct vfsops {', 'struct vfsops { int extra;')
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                stats.linked_getter(raw, segments, symbols, header)


if __name__ == '__main__':
    unittest.main()
