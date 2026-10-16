# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic exact-wire config boundaries and realistic failed transfer rows."""
import copy
import unittest
from tools.rpi5 import rp1_config_trace_serial_core as p
from tools.rpi5.tests.test_pcie_link_elapsed_serial import LinkElapsedSerialTests


class ConfigTraceSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=LinkElapsedSerialTests().fixture()
        data=data.replace(b'PCIE_ID_LINK_ELAPSED_TRIAL',b'RP1_CONFIG_TRACE_TRIAL')
        report['boot_markers']=[v.replace('PCIE_ID_LINK_ELAPSED_TRIAL','RP1_CONFIG_TRACE_TRIAL') for v in report['boot_markers']]
        report['trace_contract']['end_format']=p.package_source.TRACE_END
        report['rp1_config_trace']=dict(end_fields=p.package_source.profile.FIELDS,
            snapshot_reads_max=32,selector_writes_max=32,endpoint_writes=0,
            phase14_means='RP1_INSPECTING',link_clock_and_config_cores_unchanged=True,
            extra_mmio=False,changed_permissions=False,changed_deadlines=False,
            source_corrective_change=False,physical_rp1_id_verified=False)
        suffix=(b' RP1_CALL=5 RP1_RC=0 RP1_STEP=5 RP1_PASS=1 RP1_INDEX=15 RP1_XFER_RC=0 RP1_READS=32 '
            b'RP1_PREV=00000000 RP1_VALUE=00000000 RP1_ID=00011de4 RP1_HDR=00000000 RP1_BAR0=00000000 '
            b'RP1_BAR1=00000000 RP1_SELECTOR=00100000 RP1_STATUS=0003e0b0')
        return data.replace(b'POLL_US=0',b'POLL_US=0'+suffix),report

    def test_complete_snapshot_requires_exact_success_fields(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['rp1_id_trial_pass']);self.assertFalse(result['ethernet_proven'])
        self.assertEqual(result['telemetry']['rp1_reads'],32)
        for old,new in ((b'RP1_CALL=5',b'RP1_CALL=4'),(b'RP1_RC=0',b'RP1_RC=-2'),
            (b'RP1_STEP=5',b'RP1_STEP=3'),(b'RP1_READS=32',b'RP1_READS=31'),
            (b'RP1_ID=00011de4',b'RP1_ID=ffffffff'),(b'RP1_HDR=00000000',b'RP1_HDR=00010000'),
            (b'RP1_BAR0=00000000',b'RP1_BAR0=00000004'),(b'RP1_BAR1=00000000',b'RP1_BAR1=00010000'),
            (b'RP1_SELECTOR=00100000',b'RP1_SELECTOR=00000000'),(b'RP1_STATUS=0003e0b0',b'RP1_STATUS=0003e0f0'),
            (b'RP1_PREV=00000000',b'RP1_PREV=00000001')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)

    def test_config_failure_remains_diagnostic_with_partial_read_fields(self):
        data,report=self.fixture()
        data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14')
        data=data.replace(b'RP1_CALL=5 RP1_RC=0 RP1_STEP=5 RP1_PASS=1 RP1_INDEX=15 RP1_XFER_RC=0 RP1_READS=32',
            b'RP1_CALL=3 RP1_RC=-2 RP1_STEP=2 RP1_PASS=0 RP1_INDEX=0 RP1_XFER_RC=-8 RP1_READS=0')
        self.assertFalse(p.inspect(data,report)['rp1_id_trial_pass'])
        for old,new in ((b'RP1_CALL=3',b'RP1_CALL=6'),(b'RP1_RC=-2',b'RP1_RC=-11'),
            (b'RP1_STEP=2',b'RP1_STEP=6'),(b'RP1_PASS=0',b'RP1_PASS=2'),
            (b'RP1_INDEX=0',b'RP1_INDEX=16'),(b'RP1_XFER_RC=-8',b'RP1_XFER_RC=-11'),
            (b'RP1_READS=0',b'RP1_READS=33')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)

    def test_partial_wrong_tag_duplicate_or_changed_contract_refused(self):
        data,report=self.fixture()
        for bad in (data.replace(b' RP1_STATUS=0003e0b0',b''),
            data.replace(b'RP1_CONFIG_TRACE_TRIAL',b'PCIE_ID_LINK_ELAPSED_TRIAL'),data+p.BEGIN+b'\n'):
            with self.assertRaises(ValueError):p.inspect(bad,report)
        changed=copy.deepcopy(report);changed['rp1_config_trace']['extra_mmio']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)


if __name__=='__main__':unittest.main()
