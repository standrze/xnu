# SPDX-License-Identifier: BSD-2-Clause
"""Exact shared startup oracle and preserved real failed trial; no target execution."""
import hashlib
import json
from pathlib import Path
import unittest
from tools.rpi5 import root41_batch_trial_v2 as core
from tools.rpi5.tests import test_root41_batch_trial as fixture


class PwdOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.BatchTests.setUpClass()
        cls.files=fixture.BatchTests.files
        cls.root=fixture.package.ROOT

    def batch(self):
        return fixture.batch(self.files).replace(b'\n/\n',b'\n'+b'\n'.join(core.PWD_STARTUP)+b'\n/\n')

    def test_exact_prolog_and_all_eight_outputs_without_process_exit_claim(self):
        raw=self.batch();result=core.inspect_batch(raw,fixture.NONCE,self.files)
        self.assertEqual(len(result['commands']),8)
        self.assertTrue(result['actual_apple_pwd_physical_root'])
        self.assertTrue(result['metadata']['raw_metadata_accepted'])
        self.assertFalse(result['batch_process_exit_verified'])
        for key in ('ssh_daemon','ssh_transport','networking'):self.assertFalse(result[key])
        with self.assertRaises(ValueError):core.original.inspect_batch(raw,fixture.NONCE,self.files)

    def test_future_recorder_is_explicitly_v2_without_mutating_original(self):
        from tools.rpi5 import serial_root41_trial_v2 as recorder
        from tools.rpi5 import serial_root41_trial as previous
        self.assertEqual(recorder.trial.__globals__['core'].__file__,core.__file__)
        self.assertEqual(recorder.main.__globals__['trial'].__code__,recorder.trial.__code__)
        self.assertEqual(core.commands.__globals__['inspect_batch'].__code__,core.inspect_batch.__code__)
        self.assertEqual(previous.trial.__globals__['core'].__file__,core.original.__file__)
        pins=recorder.source_pins()
        for path in (Path(recorder.__file__),Path(core.__file__),Path(__file__)):
            self.assertEqual(pins[str(path.resolve())],hashlib.sha256(path.read_bytes()).hexdigest())
        report={'image_sha256':'a'*64}
        self.assertIn('ROOT41_V2_CAPTURE_ARMED',recorder.armed_line(report))
        self.assertNotEqual(recorder.armed_line(report),previous.armed_line(report))

    def test_missing_duplicate_reordered_unknown_or_wrong_path_prolog_rejected(self):
        raw=self.batch();prefix=b'\n'.join(core.PWD_STARTUP)
        replacements=[b'',b'\n'.join(reversed(core.PWD_STARTUP)),prefix+b'\n'+core.PWD_STARTUP[0],
            prefix.replace(b':TSD',b':UNKNOWN'),prefix+b'\nUNEXPECTED OUTPUT']
        for value in replacements:
            with self.subTest(value=value),self.assertRaises(ValueError):
                core.inspect_batch(raw.replace(prefix,value),fixture.NONCE,self.files)
        for before,after in ((b'\n/\n',b'\n/etc\n'),(b':pwd:E:0',b':pwd:E:1'),
                            (core.CRYPTO_PASS,b'RPI5XNU:SSHCRYPTO:FAIL'),(b':END:0',b':END:1')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                core.inspect_batch(raw.replace(before,after),fixture.NONCE,self.files)

    def test_frozen_physical_failure_observes_all_eight_but_never_final_exit(self):
        capture=self.root/'build/rpi5/root41-serial-20261013'
        state=json.loads((capture/'state.json').read_text());raw=(capture/'serial.bin').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'50265fdfb7805cc81d225ecf67ac4242df3cfd2d07043cb628716b9d70c37005')
        self.assertEqual(state['status'],'failed');self.assertEqual(state['error'],'Actual pwd output differs')
        self.assertEqual(state['transmitted_bytes'],585);self.assertFalse(state['command_tests_passed'])
        self.assertEqual([r['name'] for r in state['exchanges']],['identity','batch'])
        row=state['exchanges'][1];body=raw[row['offset']:row['offset']+row['bytes']]
        self.assertEqual(hashlib.sha256(body).hexdigest(),row['response_sha256'])
        result=core.inspect_batch(body,state['nonce'],self.files)
        self.assertTrue(result['batch_framing_and_all_eight_statuses_zero'])
        self.assertTrue(result['actual_apple_pwd_physical_root'])
        self.assertFalse(result['batch_process_exit_verified'])
        self.assertNotIn(('B41:'+state['nonce']+':RECOVERY_STATUS:0').encode(),raw)
        for key in ('actual_zsh_smoke','actual_ssh_buffer','actual_chacha_poly1305_public_kats','canonical_multicall_utilities'):
            self.assertTrue(result[key])


if __name__=='__main__':unittest.main()
