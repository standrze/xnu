# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import pcie_owner_trace_serial_core as p
from tools.rpi5.tests import test_rp1_bars_root_serial as bars
from tools.rpi5.tests import test_pcie_root_route_serial as old


class OwnerSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=bars.BarsSerialTests().fixture()
        rows=(b'FW AVAILABLE=1 STAGE=8 RC=0 STATE=3 SEQ=3611 FREQ=1000000 LAST=57800 DEADLINE=9000000',
            b'RPC STAGE=9 CALLS=3612 FID=c2007f12 X0=0000000000000000 X1=0000000000000e1b X2=000000000000e1c8 X3=000000000000001f',
            b'PM STAGE=7 RC=0 STATE=3 CHECKS=25282 CALLBACKS=101136 FIRST=983040 COUNT=979000',
            b'TIME START=100 LAST=57890 DEADLINE=12000100',b'IRQ STAGE=9 RC=0 STATE=3 CALLBACKS=61')
        data=data.replace(p.PREFIX+b'END ',b'\r\n'.join(p.PREFIX+r for r in rows)+b'\r\n'+p.PREFIX+b'END ')
        data=data.replace(b'RP1_BARS_ROOT_TRIAL',b'PCIE_OWNER_TRACE_TRIAL')
        report['boot_markers']=[v.replace('RP1_BARS_ROOT_TRIAL','PCIE_OWNER_TRACE_TRIAL') for v in report['boot_markers']]
        report['trace_contract']=p.package_source.trace_contract();report['owner_trace']=p.package_source.owner_contract()
        return data,report

    def test_success_exact_stages_and_nonclaims(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['bars_trial_pass']);self.assertEqual(result['observed_field_rows'],19)
        self.assertFalse(result['physical_failure_cause_proven']);self.assertFalse(result['ethernet_proven'])
        for before,after in ((b'CHECKS=25282',b'CHECKS=65537'),(b'AVAILABLE=1',b'AVAILABLE=2'),
            (b'CALLS=3612',b'CALLS=3611'),(b'X0=0000000000000000',b'X0=fffffffffffffffb')):
            with self.assertRaises(ValueError):p.inspect(data.replace(before,after),report)

    def test_every_owner_row_required_and_full_capture_health(self):
        data,report=self.fixture()
        for row in [r for r in data.splitlines(keepends=True) if any(r.startswith(p.PREFIX+label.encode()+b' ') for label in ('FW','RPC','PM','TIME','IRQ'))]:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        for marker in p.prior.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete'):p.inspect(data+marker+b' fixture\n',report)
        changed=copy.deepcopy(report);changed['owner_trace']['added_smc']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_original_capture_api(self):
        method=old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_nested_pm_failure_stays_diagnostic_failure(self):
        data,report=self.fixture()
        data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14').replace(b'GUARD=0',b'GUARD=4')
        data=re.sub(p.PREFIX+rb'BARS [^\r\n]*',p.PREFIX+b'BARS BARS_CALL=1 BARS_RC=-4 BARS_STATE=6 BARS_SLOT=0 BARS_TXNS=9 BARS_WRITES=0 BARS_PRESENT=00',data)
        for i in range(6):data=re.sub(p.PREFIX+f'BAR{i} '.encode()+rb'[^\r\n]*',
            p.PREFIX+f'BAR{i} ORIGINAL=00000000 MASK=00000000 SIZE=00000000 PLAN=00000000 CPU_START=0 CPU_END=0'.encode(),data)
        data=re.sub(p.PREFIX+rb'FW [^\r\n]*',p.PREFIX+b'FW AVAILABLE=1 STAGE=6 RC=-1 STATE=4 SEQ=9361 FREQ=1000000 LAST=250000 DEADLINE=9000000',data)
        data=re.sub(p.PREFIX+rb'RPC [^\r\n]*',p.PREFIX+b'RPC STAGE=5 CALLS=9363 FID=c2007f12 X0=0000000000000000 X1=0000000000000000 X2=0000000000000000 X3=0000000000000000',data)
        data=re.sub(p.PREFIX+rb'PM [^\r\n]*',p.PREFIX+b'PM STAGE=6 RC=-1 STATE=4 CHECKS=65536 CALLBACKS=262152 FIRST=983040 COUNT=960000',data)
        data=re.sub(p.PREFIX+rb'IRQ [^\r\n]*',p.PREFIX+b'IRQ STAGE=8 RC=0 STATE=4 CALLBACKS=61',data)
        result=p.inspect(data,report)
        self.assertFalse(result['bars_trial_pass']);self.assertFalse(result['physical_failure_cause_proven'])
        self.assertEqual(result['owner_telemetry']['pm']['checks'],65536)
        self.assertEqual(result['endpoint_config_writes'],0)


if __name__=='__main__':unittest.main()
