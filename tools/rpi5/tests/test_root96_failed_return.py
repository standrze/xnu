# SPDX-License-Identifier: BSD-2-Clause
"""Failed-boot evidence is never promoted to terminal runtime success."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import capture_root96_failed_return as capture


class FailedReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=capture.recorder.staging.ROOT/'build/rpi5/root96-serial-20261013'
        cls.plan,cls.installed,cls.state,cls.bound=capture.load_failed(cls.directory)

    def test_actual_failed_zero_tx_preserved_and_new_linux_witness_separate(self):
        self.assertEqual(self.state['status'],'failed');self.assertEqual(self.state['transmitted_bytes'],0)
        boot='6879aaf3-a600-4bd8-9f42-1e5cfbfbad35'
        returned=dict(host=self.plan['host'],boot_id=boot,
            identity=dict(identity=self.plan['identity_binding']['expected'],boot_id=boot,hostname='kamidana'),
            root=self.plan['identity_binding']['expected']['root'].split(),
            bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
            installation=self.installed,serial_sha256=self.state['serial_sha256'],
            return_source_sha256=capture.audit.return_source_pins(),observed_utc='2026-10-13T13:30:00+00:00')
        self.assertEqual(capture.validate_return(returned,self.plan,self.installed,self.state),boot)
        for key,value in (('boot_id',self.plan['linux_boot_id']),('read_only',1),('root',['/dev/mmcblk0p2','ext4','wrong'])):
            bad=copy.deepcopy(returned);bad[key]=value
            with self.assertRaises(ValueError):capture.validate_return(bad,self.plan,self.installed,self.state)

    def test_passed_or_nonzero_tx_state_is_rejected_not_reclassified(self):
        original=Path.read_text
        for key,value in (('status','passed'),('transmitted_bytes',1),('command_tests_passed',True)):
            bad=copy.deepcopy(self.state);bad[key]=value
            def read(path,*args,**kwargs):
                return json.dumps(bad) if path==self.directory/'state.json' else original(path,*args,**kwargs)
            with patch.object(Path,'read_text',read),self.assertRaises(ValueError):capture.load_failed(self.directory)


if __name__=='__main__':unittest.main()
