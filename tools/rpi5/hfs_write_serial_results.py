# SPDX-License-Identifier: BSD-2-Clause
"""Same-boot serial readback of five fixed write vectors; not durability."""
import secrets

from hfs_read_results import frame_markers, parse_validated_frame
from hfs_write_results import expected_entries
from serial_shell_trial import MAX_COMMAND_BYTES, command


def validate_entry(entry):
    if entry not in expected_entries() or set(entry) != {'path', 'bytes', 'sha256'} or type(entry['bytes']) is not int:
        raise ValueError('Only the five exact write vectors are allowed')


def parse_file(data, entry, nonce):
    validate_entry(entry)
    return parse_validated_frame(data, entry, nonce)


def read_file(fd, output, entry, progress):
    validate_entry(entry)
    nonce = 'H' + secrets.token_hex(8)
    begin, end = frame_markers(nonce)
    text = (f'echo {begin.decode()} && hexdump /mnt/hfs{entry["path"]}'
            f' && echo {end.decode()}')
    response = command(fd, output, text, [begin, end], progress, seconds=120, max_bytes=MAX_COMMAND_BYTES)
    return parse_file(response, entry, nonce)
