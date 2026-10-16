# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import unittest
from tools.rpi5 import gem_cpu_ring_retry_serial as p
from tools.rpi5.tests import test_gem_dma_batch_serial as batch_fixture

class RetrySerialTests(unittest.TestCase):
    def fixture(self,actual_report=None):
        data,report=batch_fixture.BatchSerialTests().fixture(actual_report)
        data=data.replace(p.old.BEGIN,p.BEGIN,1)
        data=data.replace(p.PREFIX+b'DMA_OWNER PREPARE=2 STATE=10 ATTEMPTED=1 ACTIVE=0 REVOKED=0 DISABLED=1 RECORD=1',
            p.PREFIX+b'DMA_PREP STEP=17 ERROR=0 BYTES=32768 PACKETS=0\n'+
            p.PREFIX+b'DMA_OWNER PREPARE=2 STATE=10 ATTEMPTED=1 ACTIVE=0 REVOKED=0 DISABLED=0 RECORD=1',1)
        data=data.replace(b'BYTES=294912',b'BYTES=32768',1)
        return data,report
    def test_complete_capture_and_all_changed_fields(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['cpu_ring_retry_trial_pass']);self.assertEqual(result['ordered_preparation_steps_completed'],17)
        self.assertEqual((result['descriptor_writes'],result['descriptor_readbacks'],result['packet_spans']),(640,640,0))
        self.assertTrue(result['automatic_watchdog_return_observed']);self.assertFalse(result['dma'])
        for before,after in ((b'STEP=17',b'STEP=16'),(b'ERROR=0 BYTES=32768 PACKETS=0',b'ERROR=-9 BYTES=32768 PACKETS=0'),
            (b'PACKETS=0',b'PACKETS=1'),(b'DISABLED=0',b'DISABLED=1'),(b'BYTES=32768',b'BYTES=49152'),
            (b'WRITTEN=640',b'WRITTEN=624'),(b'READ=640',b'READ=624'),(b'CALLS=81',b'CALLS=80'),(b'CHECKS=164',b'CHECKS=163')):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
    def test_fault_and_missing_watchdog_return_rejected(self):
        data,report=self.fixture()
        with self.assertRaises(ValueError):p.inspect(data+b'panic(cpu 0): tail\n',report)
        cut=data.index(b'RPi: BOOTSYS release VERSION:')
        with self.assertRaises(ValueError):p.inspect(data[:cut],report)
        changed=copy.deepcopy(report);changed['tag']='b'*32
        with self.assertRaises(ValueError):p.inspect(data,changed)

if __name__=='__main__':unittest.main()
