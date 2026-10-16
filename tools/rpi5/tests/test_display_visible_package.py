# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_display_visible_package as check
from .test_display_visible_serial import DisplayVisibleSerialTests
class DisplayVisiblePackageTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('RPI5_DISPLAY_VISIBLE_PACKAGE'):self.skipTest('Explicit immutable package required')
        self.package=Path(os.environ['RPI5_DISPLAY_VISIBLE_PACKAGE']).resolve();self.path=self.package/'manifest.json';self.m=json.loads(self.path.read_text())
    def test_actual_linked_report_with_actual_c_formatter(self):
        report=check.inspect(self.package,check.b.sha(self.path));DisplayVisibleSerialTests.setUpClass()
        try:
            raw,_=DisplayVisibleSerialTests().fixture(report)
            from tools.rpi5 import display_visible_serial as protocol
            self.assertTrue(protocol.inspect(raw,report)['visible_store_pass'])
            partial,_=DisplayVisibleSerialTests().fixture(report,failure=3)
            result=protocol.inspect(partial,report)
            self.assertTrue(result['allocation_trial_pass']);self.assertFalse(result['visible_store_pass']);self.assertFalse(result['diagnostic_pass'])
            with self.assertRaises(ValueError):protocol.inspect(raw+b'panic: late\r\n',report)
        finally:DisplayVisibleSerialTests.tearDownClass()
    def test_closure_architecture_authority_negative_controls(self):
        read=Path.read_text
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):
            bad=copy.deepcopy(self.m);bad[key].pop(next(iter(bad[key])))
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
        for key in ('no_retry','direct_reset_to_bl31_required','empty_fifo_is_not_prior_request_proof'):
            bad=copy.deepcopy(self.m);bad['allocation_contract'][key]=False
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
        with self.assertRaises(ValueError):check.inspect(self.package,'0'*64)
        for key,value in (('framebuffer_reads',1),('no_mapping',False),('stores',20481)):
            bad=copy.deepcopy(self.m);bad['visible_contract'][key]=value
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
    def test_type_substitutions_never_satisfy_exact_manifest(self):
        read=Path.read_text
        for path,value in ((('allocation_contract','no_retry'),1),(('allocation_contract','max_tx'),4.0),
            (('watchdog','already_active_required'),1),(('watchdog','countdown_write_once_seconds'),15.0),
            (('commands',0,'returncode'),False),(('image_bytes',),float(self.m['image_bytes'])),
            (('output_limit_bytes',),32768.0),(('stack_budget','required_margin'),512.0),(('visible_contract','stores'),20480.0)):
            bad=copy.deepcopy(self.m);node=bad
            for key in path[:-1]:node=node[key]
            node[path[-1]]=value
            def fake(p,*a,**k):return json.dumps(bad) if p==self.path else read(p,*a,**k)
            with self.subTest(path=path),patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
if __name__=='__main__':unittest.main()


