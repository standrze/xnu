# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_display_query_package as check
from .test_display_query_serial import DisplayQuerySerialTests
class DisplayQueryPackageTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('RPI5_DISPLAY_QUERY_PACKAGE'):self.skipTest('Explicit immutable package required')
        self.package=Path(os.environ['RPI5_DISPLAY_QUERY_PACKAGE']).resolve();self.path=self.package/'manifest.json';self.m=json.loads(self.path.read_text())
    def test_actual_linked_report_with_actual_c_formatter(self):
        report=check.inspect(self.package,check.b.sha(self.path));DisplayQuerySerialTests.setUpClass()
        try:
            raw,_=DisplayQuerySerialTests().fixture(report)
            from tools.rpi5 import display_query_serial as protocol
            self.assertTrue(protocol.inspect(raw,report)['query_pass'])
            with self.assertRaises(ValueError):protocol.inspect(raw+b'panic: late\r\n',report)
        finally:DisplayQuerySerialTests.tearDownClass()
    def test_closure_architecture_authority_negative_controls(self):
        read=Path.read_text
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):
            bad=copy.deepcopy(self.m);bad[key].pop(next(iter(bad[key])))
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
        for key in ('no_retry','direct_reset_to_bl31_required','empty_fifo_is_not_prior_request_proof'):
            bad=copy.deepcopy(self.m);bad['query_contract'][key]=False
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
        with self.assertRaises(ValueError):check.inspect(self.package,'0'*64)
if __name__=='__main__':unittest.main()
