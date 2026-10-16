# SPDX-License-Identifier: BSD-2-Clause
"""Pure synthetic complete write transcripts; no physical write claims."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hfs_write_acceptance as acceptance
import hfs_write_serial_results as files
from hfs_write_results import VECTORS, payload
from tools.rpi5.tests import test_serial_hfs_write_trial as serial_tests


def bundle():
    trial = acceptance.trial
    plan = dict(new_image_sha256='a' * 64, linux_boot_id='54b2ad20-73c0-4dc2-a6b7-c96506b04a0a',
                evidence_sha256={'write_preflight': 'b' * 64})
    installed = dict(image_sha256=plan['new_image_sha256'])
    bound = {name: 'c' * 64 for name in ('inputs', 'plan', 'result', 'remote_source')}
    raw = serial_tests.WriteRecorderTests().raw()
    admission = trial.validate_boot(raw)
    raw += b'W0000000000000001\r\r\nxnu:/# ls /dev\r\r\ndisk0s2\r\r\n'
    raw += trial.mount_marker('MOUNTED') + b'\r\r\n' + trial.mount_marker('STATUS') + b'\r\r\n'
    raw += trial.BATCH + b'\r\r\n'
    commands = ['echo W0000000000000001', 'ls /dev', 'hfsrw mount', 'hfsrw status', 'hfswrite exercise']
    reads = []
    for index, (entry, (_, length, seed)) in enumerate(zip(files.expected_entries(), VECTORS)):
        nonce = 'H' + format(index + 1, '016x'); begin, end = files.frame_markers(nonce)
        content = payload(length, seed)
        rows = [content[n:n+16].hex(' ').encode() + (b' ' if len(content[n:n+16]) < 16 else b'')
                for n in range(0, length, 16)]
        frame = b'\r\r\n'.join([begin, *rows, end]) + b'\r\r\n'
        raw += frame; reads.append(files.parse_file(frame, entry, nonce))
        commands.append(f'echo {begin.decode()} && hexdump /mnt/hfs{entry["path"]} && echo {end.decode()}')
    raw += trial.mount_marker('UNMOUNTED') + b'\r\r\n'
    raw += b'hfsrw mounted identity/write guard: errno 22\r\r\nUNMOUNTED_0000000000000001\r\r\n'
    raw += b'W0000000000000002\r\r\nxnu:/# '
    commands += ['hfsrw unmount', 'hfsrw status || echo UNMOUNTED_0000000000000001', 'echo W0000000000000002']
    state = dict(status='batch_passed_not_durability', partition='/dev/disk0s2', baud=115200,
        image_sha256=plan['new_image_sha256'], linux_boot_id_before_write=plan['linux_boot_id'],
        write_batch_attempts=1, hfs_mounted=False, durability_verified=False, checks=trial.CHECKS,
        evidence_sha256=bound, write_input_sha256=plan['evidence_sha256'], admission=admission, reads=reads,
        bytes=len(raw), serial_sha256=hashlib.sha256(raw).hexdigest(),
        transmitted_bytes=sum(len(text.encode()) + 1 for text in commands))
    return state, raw, plan, installed, bound


class WriteAcceptanceTests(unittest.TestCase):
    def test_full_raw_batch_and_all_five_vectors_are_independently_parsed(self):
        data = bundle(); result = acceptance.validate(*data)
        self.assertEqual(result['reads'], data[0]['reads'])
        self.assertEqual(result['transmitted_bytes'], data[0]['transmitted_bytes'])
        self.assertTrue(result['nonforced_unmount_verified']); self.assertIs(result['durability_verified'], False)

    def test_bad_state_even_with_intact_raw_fails(self):
        faults = {'status': 'failed', 'partition': '/dev/disk0s1', 'baud': True, 'image_sha256': '0' * 64,
                  'linux_boot_id_before_write': 'other', 'write_batch_attempts': True, 'hfs_mounted': True,
                  'durability_verified': True, 'checks': [], 'evidence_sha256': {}, 'write_input_sha256': {},
                  'bytes': False, 'serial_sha256': '0' * 64, 'transmitted_bytes': 0}
        original = bundle()
        for key, value in faults.items():
            data = copy.deepcopy(original); data[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): acceptance.validate(*data)

    def test_even_self_consistent_raw_hash_cannot_hide_bad_framing_mount_order_or_reset(self):
        state, raw, plan, installed, bound = bundle(); trial = acceptance.trial
        begin, end = files.frame_markers(state['reads'][0]['nonce'])
        variants = [raw + trial.TERMINAL_LOADER + b'\n', raw + b'panic(cpu',
                    raw.replace(trial.mount_marker('UNMOUNTED'), b'UNMOUNT FAILED'),
                    raw.replace(trial.BATCH, b'NOT_FSYNCED'), raw + trial.BATCH + b'\n',
                    raw.replace(begin + b'\r\r\n', b'', 1), raw + b'\n' + end + b'\n',
                    raw.replace(b'14 5d', b'ff 5d', 1),
                    raw.replace(b'W0000000000000002', b'W0000000000000001'),
                    raw.replace(b'UNMOUNTED_0000000000000001', b'UNMOUNTED_bad'),
                    raw.replace(b'hfsrw mounted identity/write guard: errno 22', b'unknown command'),
                    raw.replace(b'disk0s2\r\r\n', b'disk0s1\r\r\n'),
                    raw[:-len(b'xnu:/# ')],
                    raw.replace(trial.mount_marker('STATUS') + b'\r\r\n', b'', 1) + trial.mount_marker('STATUS') + b'\n']
        for index, changed in enumerate(variants):
            self.assertNotEqual(changed, raw, index)
            state = copy.deepcopy(bundle()[0]); state.update(bytes=len(changed), serial_sha256=hashlib.sha256(changed).hexdigest())
            with self.subTest(index=index), self.assertRaises(ValueError): acceptance.validate(state, changed, plan, installed, bound)

    def test_duplicate_read_nonce_bad_admission_or_bool_file_length_is_not_coverage(self):
        for fault in ('nonce', 'path', 'hash', 'bool', 'admission'):
            state, raw, plan, installed, bound = bundle()
            if fault == 'nonce': state['reads'][1]['nonce'] = state['reads'][0]['nonce']
            if fault == 'path': state['reads'].reverse()
            if fault == 'hash': state['reads'][0]['sha256'] = '0' * 64
            if fault == 'bool': state['reads'][1]['bytes'] = False
            if fault == 'admission': state['admission']['epoch'] = True
            with self.subTest(fault=fault), self.assertRaises(ValueError): acceptance.validate(state, raw, plan, installed, bound)


if __name__ == '__main__': unittest.main()
