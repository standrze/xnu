# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic complete-file capture faults only; no serial, mount or Pi I/O."""
import hashlib
import unittest
from unittest.mock import patch

from tools.rpi5 import hfs_read_results as hfs


class HFSReadResultsTests(unittest.TestCase):
    nonce = 'H0123456789abcdef'

    def entry(self, data, path='/etc/cross-page.bin'):
        return {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def response(self, data):
        begin, end = hfs.frame_markers(self.nonce)
        rows = []
        for offset in range(0, len(data), 16):
            row = data[offset:offset + 16]
            rows.append(row.hex(' ').encode() + (b' ' if len(row) < 16 else b''))
        return b'\n'.join([b'echo ' + begin + b' && hexdump /mnt/hfs/etc/cross-page.bin',
                            begin, *rows, end, b'xnu:/# '])

    def test_complete_empty_partial_full_and_cross_page_files(self):
        for data in (b'', b'x', bytes(range(16)), bytes(range(256)) * 129 + b'GATE4 END\n'):
            with self.subTest(size=len(data)):
                response = self.response(data)
                for ending in (b'\n', b'\r\n', b'\r\r\n'):
                    result = hfs.parse_file(response.replace(b'\n', ending), self.entry(data), self.nonce)
                    self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())
                    self.assertEqual(result['bytes'], len(data))
        self.assertGreater(len(response), 65536)

    def test_missing_duplicate_wrong_nonce_and_echo_only_frames_fail(self):
        data = b'abc'
        response = self.response(data)
        begin, end = hfs.frame_markers(self.nonce)
        variants = [response.replace(begin + b'\n', b'', 1), response + b'\n' + begin,
                    response + b'\n' + end, response.replace(end, b'WRONG'),
                    b'echo ' + begin + b' && echo ' + end + b'\nxnu:/# ',
                    end + b'\n' + begin + b'\n', response.replace(b'\n', b'\r', 1)]
        for variant in variants:
            with self.subTest(response=variant[:80]), self.assertRaises(ValueError):
                hfs.parse_file(variant, self.entry(data), self.nonce)

    def test_torn_extra_reordered_corrupt_or_chattering_rows_fail(self):
        data = bytes(range(35))
        response = self.response(data)
        lines = response.split(b'\n')
        variants = [b'\n'.join(lines[:3] + lines[4:]),
                    b'\n'.join(lines[:3] + [lines[2]] + lines[3:]),
                    b'\n'.join(lines[:2] + [lines[3], lines[2]] + lines[4:]),
                    response.replace(b'00 01', b'ff 01'),
                    response.replace(b'00 01', b'0 01'),
                    response.replace(b'20 21 22 ', b'20 21 22'),
                    response.replace(b'20 21 22 ', b'20 21 22 23 '),
                    response.replace(b'00 01', b'kernel chatter\n00 01'),
                    response.replace(b'00 01', b'00\r 01'),
                    response.replace(b'\n', b'\r\r\r\n')]
        for variant in variants:
            with self.subTest(response=variant[:100]), self.assertRaises(ValueError):
                hfs.parse_file(variant, self.entry(data), self.nonce)

    def test_invalid_reference_is_rejected_before_transmission(self):
        valid = self.entry(b'abc')
        for changed in ({**valid, 'path': '/etc/../etc/proof.txt'},
                        {**valid, 'path': ['/etc/proof.txt']},
                        {**valid, 'path': '/etc/proof.txt; reboot'},
                        {**valid, 'bytes': True}, {**valid, 'bytes': 65537},
                        {**valid, 'bytes': -1}, {**valid, 'sha256': '0' * 63}):
            with self.subTest(entry=changed), patch.object(hfs, 'command') as command:
                with self.assertRaises(ValueError):
                    hfs.read_file(1, None, changed, {'transmitted_bytes': 0})
                command.assert_not_called()

    def test_reader_opts_into_bounded_large_capture_and_hashes_result(self):
        data = bytes(range(256)) * 129 + b'GATE4 END\n'
        with patch.object(hfs.secrets, 'token_hex', return_value=self.nonce[1:]):
            with patch.object(hfs, 'command', return_value=self.response(data)) as command:
                result = hfs.read_file(1, None, self.entry(data), {'transmitted_bytes': 0})
        self.assertEqual(result['sha256'], self.entry(data)['sha256'])
        self.assertEqual(command.call_args.kwargs, {'seconds': 120, 'max_bytes': 262144})
        self.assertIn(' && hexdump /mnt/hfs/etc/cross-page.bin && echo ', command.call_args.args[2])

    def test_noncanonical_nonce_and_oversized_response_fail(self):
        for nonce in ('', 'H0123456789abcdeF', 'H0123456789abcdef; reboot'):
            with self.assertRaises(ValueError):
                hfs.parse_file(self.response(b''), self.entry(b''), nonce)
        with self.assertRaises(ValueError):
            hfs.parse_file(b' ' * 262145, self.entry(b''), self.nonce)


if __name__ == '__main__':
    unittest.main()
