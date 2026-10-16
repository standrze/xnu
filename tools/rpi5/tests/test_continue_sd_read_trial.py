# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic continuation guards; no serial/device access."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import continue_sd_read_trial as runner


class ContinuationTests(unittest.TestCase):
    now = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)

    def bundle(self):
        rows = [dict(lba=lba, sha256=hashlib.sha256(bytes([n]) * 512).hexdigest())
                for n, lba in enumerate((0, 1, 2047, 2048, 1050623, 1050624, 125173760, 250347519))]
        raw = b'\n'.join((runner.TERMINAL_LOADER, runner.SD_LOADER,
              b'RPI5XNU:SD:READ_ONLY_READY SECTORS=250347520 BLOCK=512 DMA=0 WRITES=0',
              b'RPI5XNU:SHELL:READY', b'torn SMP\rlog')) + b'\n'
        for n, row in enumerate(rows[:3]):
            raw += f"xnu:/# sdread /dev/rdisk0 {row['lba']} && echo D12345678\n".encode()
            raw += f"RPI5XNU:SDREAD:SECTOR LBA={row['lba']} SECTORS=250347520 BLOCK=512 READONLY=1\n".encode()
            for index in range(16):
                raw += f'RPI5XNU:SDREAD:DATA ROW={index} HEX={(bytes([n])*32).hex()}\n'.encode()
            raw += b'RPI5XNU:SDREAD:END\nD12345678\n'
        raw += b'xnu:/# '
        state = dict(status='failed', error='list index out of range', checks=list(runner.CHECKS),
                     device='/dev/cu.usbmodem102', disk='/dev/rdisk0', sd_data_write_operations=0,
                     reference_sha256='r', preflight_sha256='p', image_sha256='i',
                     transmitted_bytes=143, bytes=len(raw), serial_sha256=hashlib.sha256(raw).hexdigest(),
                     ended_utc=self.now.isoformat(),
                     reads=[dict(**row, bytes=512, **{'pass': 1}) for row in rows[:2]])
        return state, raw, dict(identity=dict(bytes=250347520*512), sectors=rows)

    def validate(self, state, raw, reference):
        return runner.validate_previous(state, raw, reference, 'r', dict(image_sha256='i'), 'p', self.now)

    def test_completed_prefix_recovered_without_rewriting_capture(self):
        state, raw, reference = self.bundle()
        before = copy.deepcopy(state)
        recovered = self.validate(state, raw, reference)
        self.assertEqual([row['lba'] for row in recovered], [0, 1, 2047])
        self.assertEqual(state, before)

    def test_wrong_failure_image_report_or_age_rejected(self):
        state, raw, reference = self.bundle()
        for key, value in (('error', 'SD read failed'), ('status', 'passed'), ('checks', []),
                           ('image_sha256', 'changed'), ('reference_sha256', 'changed'),
                           ('preflight_sha256', 'changed'), ('reads', []),
                           ('transmitted_bytes', 0), ('sd_data_write_operations', 1),
                           ('ended_utc', (self.now-timedelta(seconds=1801)).isoformat()),
                           ('ended_utc', (self.now+timedelta(seconds=1)).isoformat())):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate({**state, key: value}, raw, reference)

    def test_rehashed_corrupt_incomplete_or_rebooted_raw_rejected(self):
        state, raw, reference = self.bundle()
        for changed in (raw[:-1], raw.replace(b'HEX=00', b'HEX=ff', 1),
                        raw.replace(b'HEX=', b'HE\rX=', 1),
                        raw.replace(b'END\nD12345678\nxnu:/# ', b'END\nxnu:/# '),
                        runner.TERMINAL_LOADER + b'\n' + raw,
                        b'panic(cpu 0)\n' + raw,
                        raw.replace(b'SHELL:READY', b'SHELL:NOT_READY')):
            updated = {**state, 'bytes': len(changed), 'serial_sha256': hashlib.sha256(changed).hexdigest()}
            with self.subTest(changed=changed[-80:]), self.assertRaises(ValueError):
                self.validate(updated, changed, reference)


if __name__ == '__main__':
    unittest.main()
