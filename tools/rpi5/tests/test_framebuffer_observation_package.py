# SPDX-License-Identifier: BSD-2-Clause
"""Optional exact saved package admission and closure mutation negatives."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_framebuffer_observation as check
from .test_framebuffer_observation_serial import FramebufferObservationSerialTests
class FramebufferObservationPackageTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('RPI5_FB_OBSERVATION_PACKAGE'):self.skipTest('Explicit distinct package path required')
        self.package=Path(os.environ['RPI5_FB_OBSERVATION_PACKAGE']).resolve();self.path=self.package/'manifest.json'
        self.manifest=json.loads(self.path.read_text());self.sha=check.b.sha(self.path)
    def test_actual_package_and_its_real_report_native_capture_api(self):
        report=check.inspect(self.package,self.sha)
        FramebufferObservationSerialTests.setUpClass()
        try:
            case=FramebufferObservationSerialTests();raw,actual_report=case.actual(report=report)
            from tools.rpi5 import framebuffer_observation_serial
            self.assertTrue(framebuffer_observation_serial.inspect(raw,actual_report)['diagnostic_pass'])
        finally:FramebufferObservationSerialTests.tearDownClass()
    def test_actual_closure_omissions_command_and_profile_mutations(self):
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
        with self.assertRaises(ValueError):check.inspect(self.package,'0'*64)
if __name__=='__main__':unittest.main()
