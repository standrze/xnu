# SPDX-License-Identifier: BSD-2-Clause
"""In-memory staging fault model; never opens media, not physical evidence."""
import hashlib
import struct
import unittest
from unittest.mock import patch

from tools.rpi5 import hfs_stage_core as core


def mbr():
    data = bytearray(512)
    data[:12] = b'TEST_FIXTURE'
    struct.pack_into('<I', data, 440, 0x5ae1f07e)
    data[446:462] = struct.pack('<B3sB3sII', 0x80, b'\xfe\xff\xff', 0x0c,
                                b'\xfe\xff\xff', 2048, 1048576)
    data[510:] = b'\x55\xaa'
    return bytes(data)


def repeated_hash(block, count):
    digest = hashlib.sha256()
    for _ in range(count):
        digest.update(block)
    return digest.hexdigest()


class CardModel:
    """Reuse 1-MiB buffers: no giant sparse file or unbounded device model."""
    def __init__(self, fault=None):
        self.original = mbr()
        self.current = self.original
        self.boot = b'\x39' * core.CHUNK_BYTES
        self.data = b'\xa5' * core.CHUNK_BYTES
        self.boot_hash = repeated_hash(self.boot, core.BOOT_BYTES // core.CHUNK_BYTES)
        self.image_hash = repeated_hash(self.data, core.DATA_BYTES // core.CHUNK_BYTES)
        self.mbr_hash = hashlib.sha256(self.original).hexdigest()
        self.copied = set()
        self.backup = {}
        self.writes = []
        self.data_reads = 0
        self.syncs = []
        self.fault = fault

    def read(self, fd, length, offset):
        if fd == 3:
            if (length, offset) == (512, 0):
                if self.fault == 'mbr-change' and self.data_reads:
                    return b'changed'.ljust(512, b'\0')
                if self.fault == 'mbr-readback' and any(row[0] == 0 for row in self.writes):
                    return self.original
                return self.current
            if core.BOOT_START <= offset < core.DATA_START:
                if self.fault == 'boot-change' and self.copied:
                    return b'\x40' * length
                return self.boot[:length]
            if core.DATA_START <= offset < core.DATA_START + core.DATA_BYTES:
                assert offset in self.copied
                self.data_reads += 1
                if self.fault == 'data-readback':
                    return b'\x40' * length
                return self.data[:length]
        if fd == 4:
            assert length == core.CHUNK_BYTES and 0 <= offset < core.DATA_BYTES
            if self.fault == 'source-short' and offset == core.DATA_BYTES - length:
                return self.data[:-1]
            if self.fault == 'source-change' and offset == core.DATA_BYTES - length:
                return b'\x40' * length
            return self.data
        if fd == 5:
            return self.backup[offset]
        raise AssertionError((fd, length, offset))

    def write(self, fd, data, offset):
        if fd == 5:
            self.backup[offset] = data
            return len(data)
        assert fd == 3
        self.writes.append((offset, len(data)))
        if offset == 0:
            assert len(self.copied) == 128 and self.data_reads == 256
            assert self.syncs == [3]
            self.current = data
        else:
            assert core.DATA_START <= offset < core.DATA_START + core.DATA_BYTES
            assert len(data) == core.CHUNK_BYTES
            self.copied.add(offset)
        return len(data)

    def stage(self):
        with patch.object(core.os, 'pread', side_effect=self.read), \
                patch.object(core.os, 'pwrite', side_effect=self.write), \
                patch.object(core.os, 'fsync', side_effect=self.syncs.append):
            return core.stage_payload(3, 4, self.original, self.mbr_hash, self.image_hash, self.boot_hash)


class HFSStageCoreTests(unittest.TestCase):
    def test_partition_plan_changes_only_empty_second_entry(self):
        old = mbr()
        updated = core.plan_mbr(old, hashlib.sha256(old).hexdigest(), core.CARD_BYTES)
        self.assertEqual(updated[:462], old[:462])
        self.assertEqual(updated[478:], old[478:])
        self.assertEqual(struct.unpack('<B3sB3sII', updated[462:478]),
                         (0, b'\xfe\xff\xff', 0xaf, b'\xfe\xff\xff', 1050624, 262144))

    def test_wrong_mbr_capacity_layout_or_existing_partition_rejected(self):
        old = mbr()
        for offset, value in ((440, 0), (446, 0), (450, 0xaf), (455, 0), (462, 1), (478, 1), (510, 0)):
            altered = bytearray(old); altered[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                core.plan_mbr(bytes(altered), hashlib.sha256(altered).hexdigest(), core.CARD_BYTES)
        for size in (core.CARD_BYTES - 512, True):
            with self.assertRaises(ValueError):
                core.plan_mbr(old, hashlib.sha256(old).hexdigest(), size)
        with self.assertRaises(ValueError):
            core.plan_mbr(old, '0' * 64, core.CARD_BYTES)

    def test_write_extents_never_allow_boot_or_unrelated_sectors(self):
        with patch.object(core.os, 'pwrite', return_value=512) as write:
            for region, offset, data in (('data', core.BOOT_START, bytes(512)),
                                        ('data', core.DATA_START - 1, bytes(512)),
                                        ('data', core.DATA_START + core.DATA_BYTES - 511, bytes(512)),
                                        ('mbr', 512, bytes(512)), ('mbr', 0, bytes(511)),
                                        ('other', 0, bytes(512)), ('data', True, bytes(512))):
                with self.subTest(region=region, offset=offset), self.assertRaises(ValueError):
                    core.card_write(3, data, offset, region=region)
            write.assert_not_called()

    def test_short_writes_and_interruptions_have_bounded_progress(self):
        with patch.object(core.os, 'pwrite', side_effect=(InterruptedError(), 2, 2)) as write:
            core.write_all(3, b'abcd', 80)
            self.assertEqual(write.call_args_list[-1].args, (3, b'cd', 82))
        for count in (0, -1, 5, True):
            with self.subTest(count=count), patch.object(core.os, 'pwrite', return_value=count), self.assertRaises(RuntimeError):
                core.write_all(3, b'abcd', 80)
        with patch.object(core.os, 'pwrite', side_effect=InterruptedError()) as write, self.assertRaises(RuntimeError):
            core.write_all(3, b'abcd', 80)
        self.assertEqual(write.call_count, 16)
        with patch.object(core.os, 'pread', side_effect=InterruptedError()) as read, self.assertRaises(RuntimeError):
            core.read_exact(3, 512, 0)
        self.assertEqual(read.call_count, 8)

    def test_complete_backup_is_fsynced_and_fully_read_back(self):
        model = CardModel()
        with patch.object(core.os, 'pread', side_effect=model.read), \
                patch.object(core.os, 'pwrite', side_effect=model.write), \
                patch.object(core.os, 'fsync', side_effect=model.syncs.append):
            result = core.backup_boot(3, 5)
        self.assertEqual(result, model.boot_hash)
        self.assertEqual(len(model.backup), 512)
        self.assertEqual(model.syncs, [5])
        self.assertEqual(model.writes, [])

    def test_data_twice_verified_before_mbr_and_boot_preserved(self):
        model = CardModel()
        result = model.stage()
        self.assertEqual(len(model.writes), 129)
        self.assertEqual(model.writes[-1], (0, 512))
        self.assertEqual(model.syncs, [3, 3])
        self.assertEqual(model.data_reads, 256)
        self.assertEqual(result['data_readbacks'], [dict(pass_number=n, bytes=core.DATA_BYTES,
                                                       sha256=model.image_hash) for n in (1, 2)])
        self.assertEqual(result['boot_partition_sha256'], model.boot_hash)

    def test_copy_source_data_boot_or_mbr_fault_prevents_publication(self):
        for fault in ('source-short', 'source-change', 'data-readback', 'boot-change', 'mbr-change'):
            model = CardModel(fault)
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                model.stage()
            self.assertFalse(any(offset == 0 for offset, size in model.writes))
            self.assertEqual(model.current, model.original)

    def test_bad_mbr_publication_is_failure_without_automatic_rewrite(self):
        model = CardModel('mbr-readback')
        with self.assertRaisesRegex(RuntimeError, 'publication readback failed'):
            model.stage()
        self.assertEqual(sum(offset == 0 for offset, size in model.writes), 1)


if __name__ == '__main__':
    unittest.main()
