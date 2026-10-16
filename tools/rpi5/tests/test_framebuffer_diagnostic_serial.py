# SPDX-License-Identifier: BSD-2-Clause
"""Actual native FDT formatter and exact diagnostic wire-schema regressions."""
import copy
import unittest
from . import test_framebuffer_observation_serial as old
from tools.rpi5 import framebuffer_diagnostic_serial as protocol
TAG=old.TAG
def preamble(report,count=19):
    head=(f'RPI5XNU:FBOBS:ENTRY TAG={report["tag"]} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n'
        'RPI5XNU:FBOBS:UART CR=0x0000000000000301 FR=0x0000000000000090 IBRD=0x0000000000000018 FBRD=0x0000000000000000 LCRH=0x0000000000000070 FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n')
    return (head+''.join(f'RPI5XNU:FBOBS:CHECK STAGE=0x{n:016X}\r\n' for n in range(1,count+1))).encode()
class DiagnosticSerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):old.FramebufferObservationSerialTests.setUpClass();cls.native=old.FramebufferObservationSerialTests()
    @classmethod
    def tearDownClass(cls):old.FramebufferObservationSerialTests.tearDownClass()
    def actual(self,report=None):
        report=report or dict(profile=protocol.PROFILE,tag=TAG,loader_live=dict(start=0x9000000,end=0x9040000))
        raw,_=self.native.actual(report=report)
        return preamble(report)+raw.split(b'\r\n',1)[1],report
    def test_actual_formatter_complete_prechecks_then_observation(self):
        raw,report=self.actual();r=protocol.inspect(raw,report)
        self.assertTrue(r['diagnostic_pass']);self.assertTrue(r['complete_observation']);self.assertFalse(r['precheck_failed'])
        self.assertEqual(r['checked_stages'],list(range(1,20)));self.assertFalse(r['receiver_path_qualified'])
        self.assertFalse(r['ownership_proven']);self.assertFalse(r['framebuffer_absence_inferred'])
    def test_each_exact_reject_classified_failed_not_absent_or_complete(self):
        _,report=self.actual()
        for stage in range(1,20):
            raw=preamble(report,stage)+f'RPI5XNU:FBOBS:REJECT STAGE=0x{stage:016X} RC=0xFFFFFFFFFFFFFFFF NO_RELOAD OBSERVATION_INCOMPLETE\r\n'.encode()
            r=protocol.inspect(raw,report);self.assertFalse(r['diagnostic_pass']);self.assertTrue(r['precheck_failed'])
            self.assertFalse(r['complete_observation']);self.assertFalse(r['framebuffer_absence_inferred'])
            self.assertEqual(r['failed_stage'],stage);self.assertEqual(r['failed_check'],protocol.STAGES[stage-1])
    def test_reordered_partial_extra_fault_and_false_rejection_rejected(self):
        raw,report=self.actual();first=b'RPI5XNU:FBOBS:CHECK STAGE=0x0000000000000001\r\n'
        mutations=[raw.replace(first,b''),raw.replace(first,first+first),raw.replace(first,first.replace(b'0001',b'0002')),
            raw.replace(b' EL2 PRECHECK ',b' EL2 '),raw.replace(b'CR=0x0000000000000301',b'CR=0x0000000000000300'),
            raw.replace(first,b'PANIC: failed\r\n'+first),raw.replace(first,b'unknown\r\n'+first),raw+raw,
            raw.replace(b'NO_RELOAD',b'RELOAD'),raw.replace(b'DRAW=0',b'DRAW=1'),raw[:-8]]
        rejected=preamble(report,4)+b'RPI5XNU:FBOBS:REJECT STAGE=0x0000000000000004 RC=0xFFFFFFFFFFFFFFFF NO_RELOAD OBSERVATION_INCOMPLETE\r\n'
        mutations.extend([rejected.replace(b'REJECT STAGE=0x0000000000000004',b'REJECT STAGE=0x0000000000000003'),
            rejected.replace(b'RC=0xFFFFFFFFFFFFFFFF',b'RC=0x0000000000000000'),rejected+first,
            rejected.replace(b'REJECT STAGE=',b'FAULT STAGE=')])
        for index,bad in enumerate(mutations):
            with self.subTest(index=index),self.assertRaises(ValueError):protocol.inspect(bad,report)
        bad=copy.deepcopy(report);bad['profile']='pi5-framebuffer-fdt-observation-only-v1'
        with self.assertRaises(ValueError):protocol.inspect(raw,bad)
if __name__=='__main__':unittest.main()
