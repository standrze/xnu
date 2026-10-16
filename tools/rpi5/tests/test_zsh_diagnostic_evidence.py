# SPDX-License-Identifier: BSD-2-Clause
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serial_zsh_diagnostic as diagnostic
from tools.rpi5.tests.test_serial_zsh_trial import boot


class DiagnosticEvidenceTests(unittest.TestCase):
    def fixture(self):
        raw = boot() + b"\nzsh: can't open input file: /etc/zsh-smoke.zsh\nxnu:/# "
        state = {'status':'failed','device':'/dev/cu.usbmodem102',
                 'ended_utc':datetime.now(timezone.utc).isoformat(),
                 'checks':['fresh_exact_extent_distinct_ramroot_shell_boot','recovery_shell_fresh_nonce'],
                 'transmitted_bytes':49,'bytes':len(raw),'serial_sha256':hashlib.sha256(raw).hexdigest(),
                 'preflight':{'image_sha256':'b3db210c0a880688bfda783e306fb6ad3473431d9a9cc68e25035d3c8fc32fd0'}}
        return raw,state

    def check(self, raw, state):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            (work/'state.json').write_text(json.dumps(state))
            (work/'serial.bin').write_bytes(raw)
            with patch.object(diagnostic.os,'open') as opened:
                result=diagnostic.evidence(work,'/dev/cu.usbmodem102')
                opened.assert_not_called()
                return result

    def test_exact_recent_failure_allows_only_preflight_not_serial(self):
        raw,state=self.fixture()
        self.assertEqual(self.check(raw,state),state)

    def test_wrong_device_image_hash_phase_or_stale_evidence_refused(self):
        raw,state=self.fixture()
        for field,value in (('device','/dev/cu.other'),('status','passed'),('transmitted_bytes',0),
                            ('serial_sha256','0'*64),('checks',[]),('ended_utc','2020-01-01T00:00:00+00:00')):
            changed=copy.deepcopy(state);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check(raw,changed)
        changed=copy.deepcopy(state);changed['preflight']['image_sha256']='0'*64
        with self.assertRaises(ValueError):self.check(raw,changed)


if __name__ == '__main__':unittest.main()
