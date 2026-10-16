# SPDX-License-Identifier: BSD-2-Clause
"""Exact root-route wire plus complete timed capture replay, no hardware."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import types
import unittest
from tools.rpi5 import pcie_root_route_serial_core as p
from tools.rpi5 import pcie_trace_evidence as evidence
from tools.rpi5.tests import test_rp1_config_trace_serial as inherited


class RootRouteSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=inherited.ConfigTraceSerialTests().fixture()
        data=data.replace(b'RP1_CONFIG_TRACE_TRIAL',b'PCIE_ROOT_ROUTE_TRIAL')
        report['boot_markers']=[v.replace('RP1_CONFIG_TRACE_TRIAL','PCIE_ROOT_ROUTE_TRIAL') for v in report['boot_markers']]
        report['trace_contract']['end_format']=p.package_source.TRACE_END
        report['root_route']=p.package_source.root_contract()
        suffix=(b' ROOT_STEP=9 ROOT_RC=0 ROOT_READS=6 ROOT_WRITES=1 ROOT_ID=271214e4 ROOT_HDR=00010000 '
            b'ROOT_BUS_BEFORE=00000000 ROOT_BUS_WANTED=00010100 ROOT_BUS_ACTUAL=00010100 ROOT_BUS_POST_LINK=00010100')
        return data.replace(b'RP1_STATUS=0003e0b0',b'RP1_STATUS=0003e0b0'+suffix),report

    def test_success_requires_exact_route_and_preserved_latency_byte(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['rp1_id_trial_pass']);self.assertFalse(result['ethernet_proven'])
        self.assertEqual(result['telemetry']['root_reads'],6)
        for old,new in ((b'ROOT_STEP=9',b'ROOT_STEP=7'),(b'ROOT_RC=0',b'ROOT_RC=-5'),
            (b'ROOT_READS=6',b'ROOT_READS=5'),(b'ROOT_WRITES=1',b'ROOT_WRITES=0'),
            (b'ROOT_ID=271214e4',b'ROOT_ID=ffffffff'),(b'ROOT_HDR=00010000',b'ROOT_HDR=00000000'),
            (b'ROOT_BUS_WANTED=00010100',b'ROOT_BUS_WANTED=00ff0100'),
            (b'ROOT_BUS_BEFORE=00000000',b'ROOT_BUS_BEFORE=ff000000'),
            (b'ROOT_BUS_ACTUAL=00010100',b'ROOT_BUS_ACTUAL=00000000'),
            (b'ROOT_BUS_POST_LINK=00010100',b'ROOT_BUS_POST_LINK=00000000')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)
        changed=data.replace(b'ROOT_BUS_BEFORE=00000000',b'ROOT_BUS_BEFORE=a5123456')
        for field in (b'WANTED',b'ACTUAL',b'POST_LINK'):
            changed=changed.replace(b'ROOT_BUS_'+field+b'=00010100',b'ROOT_BUS_'+field+b'=a5010100')
        self.assertTrue(p.inspect(changed,report)['rp1_id_trial_pass'])

    def test_failure_is_not_upgraded_and_bad_contract_or_fields_fail(self):
        data,report=self.fixture();data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=11')
        data=data.replace(b'ROOT_STEP=9 ROOT_RC=0 ROOT_READS=6',b'ROOT_STEP=5 ROOT_RC=-5 ROOT_READS=4')
        self.assertFalse(p.inspect(data,report)['rp1_id_trial_pass'])
        for old,new in ((b'ROOT_STEP=5',b'ROOT_STEP=10'),(b'ROOT_RC=-5',b'ROOT_RC=-9'),
            (b'ROOT_READS=4',b'ROOT_READS=7'),(b'ROOT_WRITES=1',b'ROOT_WRITES=2'),
            (b'PCIE_ROOT_ROUTE_TRIAL',b'RP1_CONFIG_TRACE_TRIAL')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(b' ROOT_BUS_POST_LINK=00010100',b''),report)
        changed=copy.deepcopy(report);changed['root_route']['root_write_offset']=4
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_full_inspect_capture_api_with_timed_boot_to_nvme(self):
        data,report=self.fixture();installed={'preflight':report};sources={'fixture-source':'separately-bound'}
        parsed=p.inspect(data,report);start=datetime(2026,10,13,tzinfo=timezone.utc)
        rows=[];offset=0
        for i,line in enumerate(data.splitlines(keepends=True)):
            rows.append(dict(offset=offset,bytes=len(line),monotonic=101.0+i,
                utc=(start+timedelta(seconds=i+1)).isoformat()));offset+=len(line)
        state=dict(status='captured',continuous_capture=True,pid=123,baud=115200,device='/dev/cu.usbmodemTEST',
            transmitted_bytes=0,bytes=len(data),serial_sha256=hashlib.sha256(data).hexdigest(),
            installation=installed,source_sha256=sources,physical_reset_return_proven=False,
            xnu_pe_runtime_proven=False,ethernet_proven=False,armed_monotonic=100.0,
            started_utc=start.isoformat(),armed_utc=start.isoformat(),
            ended_utc=(start+timedelta(seconds=99)).isoformat(),diagnostic=parsed,inventory=p.inventory(data))
        full=types.FunctionType(evidence.inspect_capture.__code__,dict(evidence.inspect_capture.__globals__,
            protocol=p,recorder=types.SimpleNamespace(inventory=p.inventory)))
        actual=full(data,rows,state,installed,sources)
        self.assertTrue(actual['trace_capture_valid']);self.assertEqual(actual['terminal_to_bootsys_seconds'],1.0)
        self.assertEqual(p.PREPARED_PREFIX,p.PREFIX+b'PREPARED ')
        for key,value in (('transmitted_bytes',1),('continuous_capture',False),('status','failed')):
            with self.subTest(key=key),self.assertRaises(ValueError):full(data,rows,state|{key:value},installed,sources)
        late=copy.deepcopy(rows);stop=data.index(p.PREFIX+b'END')
        for row in late:
            if row['offset']>stop:row['monotonic']+=150
        with self.assertRaises(ValueError):full(data,late,state,installed,sources)


if __name__=='__main__':unittest.main()
