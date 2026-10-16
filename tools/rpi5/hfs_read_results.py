# SPDX-License-Identifier: BSD-2-Clause
"""Bounded complete-file HFS read verification; never opens a device itself.

These helpers do not establish media identity or boot readiness. A caller must
validate the HFS package, Linux physical-partition reference and fresh boot
markers before passing an already-owned serial descriptor to read_file().
"""
import hashlib
import re
import secrets

try:
    from .serial_shell_trial import MAX_COMMAND_BYTES, command
except ImportError:
    from serial_shell_trial import MAX_COMMAND_BYTES, command

FILE_PATHS = frozenset(('/etc/proof.txt', '/etc/empty', '/etc/cross-page.bin',
                        '/etc/recovery.sh', '/bin/echo'))
MAX_FILE_BYTES = 65536


def validate_entry(entry):
    if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or
            entry['path'] not in FILE_PATHS or
            type(entry.get('bytes')) is not int or
            not 0 <= entry['bytes'] <= MAX_FILE_BYTES or
            not isinstance(entry.get('sha256'), str) or
            not re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])):
        raise ValueError('Expected a bounded, whitelisted fixture file and SHA256')


def frame_markers(nonce):
    if not isinstance(nonce, str) or not re.fullmatch(r'H[0-9a-f]{16}', nonce):
        raise ValueError('Expected a fresh canonical HFS nonce')
    return (f'RPI5XNU:HFSFILE:BEGIN:{nonce}'.encode(),
            f'RPI5XNU:HFSFILE:END:{nonce}'.encode())


def normalize_output(data):
    # Physical Pi userspace output has CR-CR-LF (tty plus UART translation),
    # while kernel logs use CR-LF. Accept only those complete line endings,
    # not arbitrary carriage returns embedded in a hex row or script line.
    normalized = re.sub(rb'\r{1,2}\n', b'\n', data)
    if b'\r' in normalized:
        raise ValueError('Torn carriage return in file response')
    return normalized


def parse_file(data, entry, nonce):
    """Hash every byte between unique nonce lines, using our hexdump grammar.

    A partial final row has a trailing space; complete 16-byte rows do not.
    No chatter, blank lines, offsets, compression or truncated rows are allowed
    inside the frame. Input echo outside it is not evidence of command output.
    """
    validate_entry(entry)
    return parse_validated_frame(data, entry, nonce)


def parse_validated_frame(data, entry, nonce):
    """Shared hex grammar, after the caller's separate fixed-file validation.

    No serial I/O here. RO and write callers keep separate immutable path/hash
    allowlists; this helper never authorizes a command or a device operation.
    """
    if (type(entry.get('bytes')) is not int or not 0 <= entry['bytes'] <= MAX_FILE_BYTES
            or not isinstance(entry.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])):
        raise ValueError('Invalid bounded frame length/hash')
    begin, end = frame_markers(nonce)
    if not isinstance(data, bytes) or len(data) > MAX_COMMAND_BYTES:
        raise ValueError('Oversized or non-byte file response')
    normalized = normalize_output(data)
    lines = normalized.split(b'\n')
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise ValueError('Missing, duplicate or torn file framing')
    start, stop = lines.index(begin), lines.index(end)
    if stop <= start:
        raise ValueError('Reversed file framing')
    rows = lines[start + 1:stop]
    size = entry['bytes']
    if len(rows) != (size + 15) // 16:
        raise ValueError('Missing or extra file rows')
    content = bytearray()
    for index, row in enumerate(rows):
        count = min(16, size - index * 16)
        pattern = rb'[0-9a-f]{2}(?: [0-9a-f]{2}){' + str(count - 1).encode() + rb'}'
        if count < 16:
            pattern += b' '
        if not re.fullmatch(pattern, row):
            raise ValueError('Malformed, partial or interleaved file row')
        content.extend(bytes.fromhex(row.decode('ascii')))
    digest = hashlib.sha256(content).hexdigest()
    if len(content) != size or digest != entry['sha256']:
        raise ValueError('Complete-file size or SHA256 differs from reference')
    return {'path': entry['path'], 'bytes': size, 'sha256': digest,
            'nonce': nonce, 'verification': 'complete_serial_hex_dump'}


def read_file(fd, output, entry, progress):
    """Called only after the recorder's media/preflight/fresh-boot guards."""
    validate_entry(entry)  # Reject unsafe paths/sizes before any transmission.
    nonce = 'H' + secrets.token_hex(8)
    begin, end = frame_markers(nonce)
    text = (f'echo {begin.decode()} && hexdump /mnt/hfs{entry["path"]}'
            f' && echo {end.decode()}')
    response = command(fd, output, text, [begin, end], progress,
                       seconds=120, max_bytes=MAX_COMMAND_BYTES)
    return parse_file(response, entry, nonce)
