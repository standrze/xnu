# SPDX-License-Identifier: BSD-2-Clause
"""Bounded disposable-card staging primitives; no device opening or discovery.

The caller must prove NVMe root, exact card identity, descriptor ownership,
unmounted media and a successful physical SD trial before granting an fd.
The only card writes permitted here are the future HFS data span and the
single MBR sector. Boot data and all unrelated sectors remain protected.
"""
import hashlib
import os
import struct

SECTOR_BYTES = 512
CARD_BYTES = 128177930240
BOOT_START = 2048 * SECTOR_BYTES
BOOT_BYTES = 1048576 * SECTOR_BYTES
DATA_START = BOOT_START + BOOT_BYTES
DATA_BYTES = 262144 * SECTOR_BYTES
CHUNK_BYTES = 1024 * 1024


def plan_mbr(original, expected_sha256, card_bytes):
    if (type(card_bytes) is not int or card_bytes != CARD_BYTES or
            not isinstance(original, bytes) or len(original) != SECTOR_BYTES or
            hashlib.sha256(original).hexdigest() != expected_sha256 or original[510:] != b'\x55\xaa' or
            struct.unpack_from('<I', original, 440)[0] != 0x5ae1f07e):
        raise ValueError('Unexpected card capacity, MBR identity, signature or hash')
    boot = original[446:462]
    if (boot[0] != 0x80 or boot[4] != 0x0c or
            struct.unpack_from('<II', boot, 8) != (2048, 1048576) or
            original[462:510] != bytes(48)):
        raise ValueError('Existing MBR is not the exact preserved one-partition layout')
    updated = bytearray(original)
    updated[462:478] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', 0xaf,
                                   b'\xfe\xff\xff', DATA_START // 512, DATA_BYTES // 512)
    updated = bytes(updated)
    if updated[:462] != original[:462] or updated[478:] != original[478:]:
        raise ValueError('Partition plan altered protected MBR bytes')
    return updated


def read_exact(fd, length, offset):
    # A short block read is a failure, not padded or silently retried evidence.
    for _ in range(8):
        try:
            data = os.pread(fd, length, offset)
            if len(data) != length:
                raise RuntimeError('Short staging/reference read')
            return data
        except InterruptedError:
            continue
    raise RuntimeError('Staging read interruption limit exceeded')


def hash_span(fd, offset, length):
    if type(offset) is not int or type(length) is not int or offset < 0 or length < 0:
        raise ValueError('Invalid read span')
    digest = hashlib.sha256()
    for start in range(offset, offset + length, CHUNK_BYTES):
        digest.update(read_exact(fd, min(CHUNK_BYTES, offset + length - start), start))
    return digest.hexdigest()


def write_all(fd, data, offset):
    """Bound short writes/EINTR; no publication is assumed on partial failure."""
    done = 0
    for _ in range(16):
        try:
            count = os.pwrite(fd, data[done:], offset + done)
        except InterruptedError:
            continue
        if type(count) is not int or count <= 0 or count > len(data) - done:
            raise RuntimeError('Invalid or stalled staging write')
        done += count
        if done == len(data):
            return
    raise RuntimeError('Staging write progress/interruption limit exceeded')


def card_write(fd, data, offset, *, region):
    if not isinstance(data, bytes) or not data or type(offset) is not int:
        raise ValueError('Expected bounded byte payload and integer card offset')
    if region == 'data':
        allowed = DATA_START <= offset and offset + len(data) <= DATA_START + DATA_BYTES
    elif region == 'mbr':
        allowed = offset == 0 and len(data) == SECTOR_BYTES
    else:
        allowed = False
    if not allowed:
        raise ValueError('Card write overlaps protected boot/unrelated sectors')
    write_all(fd, data, offset)


def backup_boot(card_fd, backup_fd):
    digest = hashlib.sha256()
    for offset in range(0, BOOT_BYTES, CHUNK_BYTES):
        data = read_exact(card_fd, CHUNK_BYTES, BOOT_START + offset)
        digest.update(data)
        write_all(backup_fd, data, offset)
    os.fsync(backup_fd)
    expected = digest.hexdigest()
    if hash_span(backup_fd, 0, BOOT_BYTES) != expected:
        raise RuntimeError('Complete boot-partition backup readback differs')
    return expected


def stage_payload(card_fd, image_fd, original_mbr, mbr_sha256, image_sha256, boot_sha256):
    """Write data first; publish only after full readback and boot preservation.

    No automatic rollback/reset on failure. The caller retains exact MBR and
    boot backups; a failed publication must be diagnosed on the same verified
    card before any restoration. This is not an electrical atomicity claim.
    """
    updated = plan_mbr(original_mbr, mbr_sha256, CARD_BYTES)
    if read_exact(card_fd, SECTOR_BYTES, 0) != original_mbr:
        raise RuntimeError('MBR changed after backup')
    if hash_span(card_fd, BOOT_START, BOOT_BYTES) != boot_sha256:
        raise RuntimeError('Boot partition changed after backup')
    source_hash = hashlib.sha256()
    for offset in range(0, DATA_BYTES, CHUNK_BYTES):
        data = read_exact(image_fd, CHUNK_BYTES, offset)
        source_hash.update(data)
        card_write(card_fd, data, DATA_START + offset, region='data')
    os.fsync(card_fd)
    if source_hash.hexdigest() != image_sha256:
        raise RuntimeError('Fixture source changed during copy; MBR not published')
    reads = []
    for attempt in (1, 2):
        actual = hash_span(card_fd, DATA_START, DATA_BYTES)
        if actual != image_sha256:
            raise RuntimeError('Complete HFS data readback differs; MBR not published')
        reads.append(dict(pass_number=attempt, bytes=DATA_BYTES, sha256=actual))
    if hash_span(card_fd, BOOT_START, BOOT_BYTES) != boot_sha256:
        raise RuntimeError('Protected boot span changed; MBR not published')
    if read_exact(card_fd, SECTOR_BYTES, 0) != original_mbr:
        raise RuntimeError('MBR changed during data copy; refusing publication')
    # The sixteen-byte partition entry is the only intended MBR difference.
    # Write one complete sector, retaining all boot code/disk ID/other entries.
    card_write(card_fd, updated, 0, region='mbr')
    os.fsync(card_fd)
    if read_exact(card_fd, SECTOR_BYTES, 0) != updated:
        raise RuntimeError('MBR publication readback failed; preserve backups for recovery')
    if hash_span(card_fd, BOOT_START, BOOT_BYTES) != boot_sha256:
        raise RuntimeError('Protected boot span changed after MBR publication')
    return dict(mbr_before_sha256=mbr_sha256, mbr_after_sha256=hashlib.sha256(updated).hexdigest(),
                boot_partition_sha256=boot_sha256, boot_partition_bytes=BOOT_BYTES,
                data_start_sector=DATA_START // 512, data_sectors=DATA_BYTES // 512,
                data_readbacks=reads, data_bytes_written=DATA_BYTES, mbr_bytes_written=512,
                publication_after_two_complete_data_readbacks=True,
                scope='Linux disposable-media staging/readback only; not XNU HFS mount or write durability')
