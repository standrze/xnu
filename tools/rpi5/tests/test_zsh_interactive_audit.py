# SPDX-License-Identifier: BSD-2-Clause
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_zsh_interactive_diagnostic as audit


class ZshInteractiveAuditTests(unittest.TestCase):
    def fixture(self):
        nonce = b'D0123456789abcdef'
        raw = b'echo ' + nonce + b'\n' + nonce + b'\nxnu:/# ' + audit.trial.LAUNCH.encode() + b'\n'
        raw += (b'DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n' * 2)
        raw += (b'pi-zsh# print version\nPI_ZSH:5.9\npi-zsh# print math\nPI_BUILTINS:xnu:42\n'
                b'pi-zsh# /bin/echo PI_EXEC_' + nonce + b'\nPI_EXEC_' + nonce + b'\npi-zsh# exit\n'
                b'xnu:/# echo RECOVERED_' + nonce + b'\nRECOVERED_' + nonce + b'\nxnu:/# ')
        state = {'status':'interactive_diagnostic_completed', 'checks':audit.CHECKS,
                 'script_file_acceptance':False, 'device':'/dev/cu.usbmodem102',
                 'transmitted_bytes':273, 'bytes':len(raw), 'nonce':nonce.decode(),
                 'serial_sha256':hashlib.sha256(raw).hexdigest()}
        return raw, state

    def test_subset_does_not_waive_script_or_complete_other_gates(self):
        raw, state = self.fixture()
        result = audit.validate(raw, state)
        self.assertTrue(result['interactive_prompts_returned'])
        for name in ('script_file_acceptance', 'full_gate6_complete', 'networking_proven', 'durability_proven'):
            self.assertFalse(result[name])

    def test_echo_missing_prompt_failure_or_scope_upgrade_rejected(self):
        raw, state = self.fixture()
        for bad in (raw.replace(b'\nPI_ZSH:5.9\n',b'\nprint PI_ZSH:5.9\n'),
                    raw.replace(b'\npi-zsh# exit',b'\nexit'), raw + b'panic(cpu 0)',
                    raw.replace(b'PI_BUILTINS:xnu:42',b'PI_BUILTINS:xnu:41')):
            changed = copy.deepcopy(state)
            changed.update(bytes=len(bad),serial_sha256=hashlib.sha256(bad).hexdigest())
            with self.assertRaises(ValueError): audit.validate(bad,changed)
        for field, value in (('script_file_acceptance',True), ('transmitted_bytes',0), ('checks',[])):
            changed = copy.deepcopy(state);changed[field]=value
            with self.assertRaises(ValueError):audit.validate(raw,changed)


if __name__ == '__main__': unittest.main()
