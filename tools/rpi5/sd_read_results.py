# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for actual BSD-device sector trial output, not a simulator."""
import hashlib
import re


def sector_lines(data):
    if not isinstance(data, bytes) or len(data) > 64 * 1024 * 1024:
        raise ValueError('Expected bounded byte capture')
    # Pi tty/UART translation can produce CR-CR-LF. Never repair a damaged
    # hex row by removing carriage returns embedded inside its contents.
    normalized = re.sub(rb'\r{1,2}\n', b'\n', data)
    if b'\r' in normalized:
        raise ValueError('Torn carriage return in sector capture')
    return normalized.split(b'\n')


def parse_sector(data, lba, sectors):
    all_lines = sector_lines(data)
    positions = [i for i, line in enumerate(all_lines) if b'RPI5XNU:SDREAD:' in line]
    lines = [all_lines[i] for i in positions]
    expected = f'RPI5XNU:SDREAD:SECTOR LBA={lba} SECTORS={sectors} BLOCK=512 READONLY=1'.encode()
    if len(lines) != 18 or lines[0] != expected or lines[-1] != b'RPI5XNU:SDREAD:END':
        raise ValueError('Missing, duplicate, torn or wrong-geometry sector output')
    if positions != list(range(positions[0], positions[0] + 18)):
        raise ValueError('Interleaved sector frame')
    sector = bytearray()
    for index, line in enumerate(lines[1:-1]):
        match = re.fullmatch(rb'RPI5XNU:SDREAD:DATA ROW=([0-9]+) HEX=([0-9a-f]{64})', line)
        if not match or match[1] != str(index).encode():
            raise ValueError('Missing, duplicate, torn or out-of-order sector row')
        sector.extend(bytes.fromhex(match[2].decode('ascii')))
    if len(sector) != 512:
        raise ValueError('Wrong sector length')
    return {'lba': lba, 'bytes': len(sector), 'sha256': hashlib.sha256(sector).hexdigest()}


def validate_sector_capture(data, expected, sectors):
    """Independently reconstruct ordered sector bytes, not report assertions.

    Expected entries contain LBA and SHA256 for every read, including repeated
    passes. Chatter outside frames is allowed; missing/extra/reordered frames
    and chatter or corruption inside a frame are not.
    """
    if not isinstance(expected, list) or not 1 <= len(expected) <= 64:
        raise ValueError('Expected bounded sector coverage')
    if not isinstance(data, bytes) or len(data) > 64 * 1024 * 1024:
        raise ValueError('Expected bounded byte capture')
    # SMP startup logs can be torn outside the sector protocol. Keep the raw
    # bytes intact; apply strict line-ending checks to each complete frame,
    # never "repair" protocol contents or ignore chatter inside a frame.
    lines = data.split(b'\n')
    positions = [i for i, line in enumerate(lines) if b'RPI5XNU:SDREAD:' in line]
    if len(positions) != 18 * len(expected):
        raise ValueError('Raw SD capture lacks exact complete sector coverage')
    actual = []
    for index, row in enumerate(expected):
        frame = positions[index * 18:(index + 1) * 18]
        if frame != list(range(frame[0], frame[0] + 18)):
            raise ValueError('Interleaved sector frame in raw capture')
        decoded = parse_sector(b'\n'.join(lines[frame[0]:frame[-1] + 1]) + b'\n', row['lba'], sectors)
        if decoded['sha256'] != row['sha256']:
            raise ValueError('Raw SD sector differs from independent reference')
        actual.append(decoded)
    return actual
