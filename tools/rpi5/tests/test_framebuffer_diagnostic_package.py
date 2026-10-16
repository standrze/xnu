# SPDX-License-Identifier: BSD-2-Clause
"""Distinct actual diagnostic package/record admission and closure negatives."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_framebuffer_diagnostic as check
from . import test_framebuffer_diagnostic_serial as serial
class DiagnosticPackageTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('RPI5_FB_DIAGNOSTIC_PACKAGE'):self.skipTest('Explicit distinct diagnostic package required')
        self.package=Path(os.environ['RPI5_FB_DIAGNOSTIC_PACKAGE']).resolve();self.path=self.package/'manifest.json'
        self.manifest=json.loads(self.path.read_text());self.sha=check.b.sha(self.path)
    def test_actual_report_native_record_schema(self):
        report=check.inspect(self.package,self.sha);serial.DiagnosticSerialTests.setUpClass()
        try:
            raw,report=serial.DiagnosticSerialTests().actual(report=report)
            self.assertTrue(serial.protocol.inspect(raw,report)['complete_observation'])
            self.assertEqual(report['early_diagnostic_stages'],19)
        finally:serial.DiagnosticSerialTests.tearDownClass()
    def test_exact_closure_commands_output_and_profile_guards(self):
        original=Path.read_text
        def invoke(m):
            def fake(path,*a,**kw):return json.dumps(m) if path==self.path else original(path,*a,**kw)
            with patch.object(Path,'read_text',fake),self.assertRaises(ValueError):check.inspect(self.package)
        for key in ('inputs_sha256','generated_sha256','headers_sha256'):
            bad=copy.deepcopy(self.manifest);bad[key].pop(next(iter(bad[key])));invoke(bad)
        bad=copy.deepcopy(self.manifest);bad['commands'][0]['command'].append('-DUNSAFE');invoke(bad)
        bad=copy.deepcopy(self.manifest);bad['physical_execution']=True;invoke(bad)
        bad=copy.deepcopy(self.manifest);bad['watchdog']['reload_after_arm']=True;invoke(bad)
        bad=copy.deepcopy(self.manifest);bad['source_scan'].pop(next(iter(bad['source_scan'])));invoke(bad)
        bad=copy.deepcopy(self.manifest);bad['profile']='pi5-framebuffer-fdt-observation-only-v1';invoke(bad)
        with self.assertRaises(ValueError):check.inspect(self.package,'0'*64)
if __name__=='__main__':unittest.main()
