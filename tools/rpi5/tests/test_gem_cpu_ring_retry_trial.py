# SPDX-License-Identifier: BSD-2-Clause
"""Package closure/mutation tests; final artifact supplied explicitly."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_gem_cpu_ring_retry_trial as c
from tools.rpi5 import qualify_gem_cpu_ring_retry_trial as q
from tools.rpi5.tests.test_gem_cpu_ring_retry_serial import RetrySerialTests

class RetryTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        keys=('RPI5_RETRY_PACKAGE','RPI5_RETRY_MANIFEST_SHA','RPI5_RETRY_STACK_QUALIFICATION','RPI5_RETRY_STACK_QUALIFICATION_SHA')
        if not all(os.environ.get(k) for k in keys):raise unittest.SkipTest('Final retry package/qualification not supplied')
        cls.package=Path(os.environ[keys[0]]).resolve();cls.pin=os.environ[keys[1]]
        cls.qualification=Path(os.environ[keys[2]]).resolve();cls.qpin=os.environ[keys[3]]
        cls.m=json.loads((cls.package/'manifest.json').read_bytes())
        with patch('subprocess.run',side_effect=AssertionError('No compiler/hardware')):cls.report=c.inspect(cls.package,cls.pin,cls.qualification,cls.qpin)
    def test_package_a76_and_strict_serial_fixture(self):
        self.assertTrue(self.report['software_trial_qualified']);self.assertFalse(self.report['physical_execution_proven'])
        data,report=RetrySerialTests().fixture(self.report)
        from tools.rpi5 import gem_cpu_ring_retry_serial as serial
        self.assertTrue(serial.inspect(data,report)['cpu_ring_retry_trial_pass'])
    def test_command_source_payload_and_manifest_mutations(self):
        with patch('subprocess.run',side_effect=AssertionError('No compiler/hardware')):
            m=copy.deepcopy(self.m);m['commands'].pop()
            with self.assertRaises(ValueError):c.canonical.command_bindings(self.package,m)
            changed=c.b.derived_sources();changed['overlay/BCM2712GEMDMABatch.cpp']+=b'\n'
            with patch.object(c.b,'derived_sources',return_value=changed):
                with self.assertRaises(ValueError):c.canonical.source_outputs(self.package,self.m)
            original=Path.read_bytes;manifest=self.package/'manifest.json'
            for key,value in (('allocation_bytes',294912),('packet_spans',1),('preparation_steps',16),('bme_enable',1),('qualification_sha256','0'*64)):
                mutant=copy.deepcopy(self.m);mutant[key]=value;raw=json.dumps(mutant,sort_keys=True).encode()
                def read(path,raw=raw):return raw if path==manifest else original(path)
                with patch.object(Path,'read_bytes',read),self.assertRaises(ValueError):c.inspect_image(self.package,hashlib.sha256(raw).hexdigest())
    def test_stack_qualification_pin_mutations(self):
        with patch('subprocess.run',side_effect=AssertionError('No compiler/hardware')):
            with self.assertRaises(ValueError):q.inspect(self.package,self.pin,self.qualification,'0'*64)

if __name__=='__main__':unittest.main()
