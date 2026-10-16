# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic syscall/output faults; no host disk or physical Pi I/O."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import sys
import time

from tools.rpi5.sd_read_results import parse_sector, validate_sector_capture

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/rpi5'))
import serial_sd_read_trial as runner
import serial_terminal_trial as terminal


class SDReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.program = Path(cls.tmp.name) / 'sdread'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        str(ROOT / 'tools/rpi5/tests/sdread_host.c'),
                        str(ROOT / 'tools/rpi5/user/sdread.c'), '-o', str(cls.program)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, *args, mode=''):
        result = subprocess.run([str(self.program), *args], env={**os.environ, 'SDREAD_FIXTURE': mode},
                                capture_output=True, timeout=10)
        self.assertNotIn(b'Sanitizer', result.stderr)
        return result

    def test_readonly_open_exact_sector_and_geometry(self):
        result = self.run_probe('/dev/rdisk0', '2048')
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = parse_sector(result.stdout, 2048, 250347520)
        self.assertEqual(parsed['sha256'], hashlib.sha256(bytes(range(256))*2).hexdigest())
        self.assertIn(b'OPENS=1 CLOSES=1 READS=1', result.stderr)

    def test_invalid_paths_numbers_and_partition_names_never_open(self):
        for path, lba in (('', '0'), ('/dev/disk0', '0'), ('/dev/rdisk0s1', '0'),
                          ('/dev/rdisk32', '0'), ('/dev/rdisk0', '-1'), ('/dev/rdisk0', '4294967296'),
                          ('/dev/rdisk0', ''), ('/dev/rdisk0/../rdisk1', '0')):
            with self.subTest(path=path, lba=lba):
                result = self.run_probe(path, lba)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'OPENS=0 CLOSES=0 READS=0', result.stderr)

    def test_failure_paths_never_emit_sector_success_and_balance_close(self):
        for mode, reads in (('ioctl', 0), ('size', 0), ('writable', 0), ('short', 1),
                            ('error', 1), ('close', 1), ('eintr', 8)):
            with self.subTest(mode=mode):
                result = self.run_probe('/dev/rdisk0', '0', mode=mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b'')
                self.assertIn(f'OPENS=1 CLOSES=1 READS={reads}'.encode(), result.stderr)
        result = self.run_probe('/dev/rdisk0', '250347520')
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'OPENS=1 CLOSES=1 READS=0', result.stderr)

    def test_parser_rejects_false_or_torn_success(self):
        data = self.run_probe('/dev/rdisk0', '0').stdout
        rows = data.splitlines(keepends=True)
        variants = [data[:-1].replace(b'READONLY=1', b'READONLY=0'), data+rows[1],
                    b''.join(rows[:4]+rows[5:]), b''.join(rows[:4]+[rows[5],rows[4]]+rows[6:]),
                    data.replace(b'HEX=', b'HEX=x', 1), data.replace(b'ROW=0', b'ROW=00', 1),
                    data.replace(b'SECTORS=250347520', b'SECTORS=2'), data.replace(b'LBA=0', b'LBA=1')]
        for variant in variants:
            with self.subTest(variant=variant[:120]), self.assertRaises(ValueError):
                parse_sector(variant, 0, 250347520)

    def test_trial_never_transmits_without_storage_boot_markers(self):
        reference = {'identity': {'bytes': 250347520*512}}
        state = {'checks': [], 'reads': [], 'transmitted_bytes': 0}
        with mock.patch.object(runner, 'wait_for_boot_markers', side_effect=TimeoutError('no SD ready')):
            with mock.patch.object(runner, 'command') as command, self.assertRaises(TimeoutError):
                runner.trial(1, None, 30, state, reference, '/dev/rdisk0')
            command.assert_not_called()
        self.assertEqual(state['transmitted_bytes'], 0)

    def test_sector_parser_accepts_only_complete_known_line_endings(self):
        data = self.run_probe('/dev/rdisk0', '0').stdout
        expected = parse_sector(data, 0, 250347520)
        for ending in (b'\n', b'\r\n', b'\r\r\n'):
            self.assertEqual(parse_sector(data.replace(b'\n', ending), 0, 250347520), expected)
        for changed in (data.replace(b'HEX=', b'HE\rX=', 1),
                        data.replace(b'SDREAD:', b'SDR\rEAD:', 1),
                        data.replace(b'\n', b'\r\r\r\n'), data + b'\r',
                        data.replace(b'ROW=1 ', b'ROW=1\r ', 1)):
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                parse_sector(changed, 0, 250347520)

    def test_sector_parser_rejects_chatter_inside_frame(self):
        data = self.run_probe('/dev/rdisk0', '0').stdout
        lines = data.splitlines(keepends=True)
        with self.assertRaises(ValueError):
            parse_sector(b''.join(lines[:3] + [b'other log\n'] + lines[3:]), 0, 250347520)
        self.assertEqual(parse_sector(b'outside\n' + data + b'outside\n', 0, 250347520)['bytes'], 512)

    def test_complete_raw_capture_reconstructs_ordered_repeated_sectors(self):
        first = self.run_probe('/dev/rdisk0', '0').stdout
        second = self.run_probe('/dev/rdisk0', '1').stdout
        expected = [parse_sector(frame, lba, 250347520)
                    for frame, lba in ((first, 0), (second, 1), (first, 0), (second, 1))]
        raw = b'ready\n' + first + second + b'prompt\n' + first + second
        self.assertEqual(validate_sector_capture(raw, expected, 250347520), expected)
        self.assertEqual(validate_sector_capture(b'torn startup\rlog\n' + raw,
                                                expected, 250347520), expected)
        for changed in (first + second, raw + first, second + first + first + second,
                        raw.replace(b'HEX=00', b'HEX=ff', 1),
                        raw.replace(b'HEX=', b'HE\rX=', 1),
                        raw.replace(b'DATA ROW=1', b'other log\rtext\nRPI5XNU:SDREAD:DATA ROW=1', 1)):
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                validate_sector_capture(changed, expected, 250347520)

    def test_nonbyte_or_oversized_parser_input_is_rejected(self):
        for data in ('not bytes', bytearray(b''), b'x' * (64 * 1024 * 1024 + 1)):
            with self.assertRaises(ValueError):
                parse_sector(data, 0, 250347520)

    def test_explicit_boot_failure_aborts_without_waiting_for_prompt(self):
        for marker in (b'panic(cpu 0', b'RPI5XPU:SD:HANDOFF RC=-4 STAGE=2'):
            output = io.BytesIO()
            with mock.patch.object(terminal.select, 'select', return_value=([1], [], [])):
                with mock.patch.object(terminal.os, 'read', return_value=marker):
                    with self.assertRaisesRegex(RuntimeError, 'boot failure before readiness'):
                        terminal.wait_for_boot_markers(1, output, time.monotonic()+5,
                                                      abort_markers=(b'panic(cpu', b':SD:HANDOFF RC=-'))
            self.assertEqual(output.getvalue(), marker)

    def test_preflight_missing_false_or_changed_image_is_rejected(self):
        image = Path(self.tmp.name) / 'fixture.bin'
        image.write_bytes(b'preflight guard fixture, not a boot image')
        valid = {'preflight_pass': True, 'sd_readonly_trial': True, 'image': str(image),
                 'image_sha256': runner.sha256(image),
                 'checks': {name: True for name in runner.REQUIRED_SD_CHECKS}}
        runner.validate_preflight(valid)
        for changed in ({**valid, 'checks': {}}, {**valid, 'sd_readonly_trial': False},
                        {**valid, 'image_sha256': '0'*64}, {**valid, 'preflight_pass': False},
                        {**valid, 'checks': {**valid['checks'], 'separate_sd_trial_flags': False}}):
            with self.assertRaises(ValueError):
                runner.validate_preflight(changed)


if __name__ == '__main__':
    unittest.main()
