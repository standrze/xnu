# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import re
import types
import unittest
from tools.rpi5 import rp1_bars_root_serial_core as p
from tools.rpi5.tests import test_pcie_root_route_serial as old


class BarsSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.RootRouteSerialTests().fixture()
        line=next(row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(p.PREFIX+b'END '))
        words=line.split()[1:];groups={'END':words[:10],'UBUS':words[10:19],'LINK':words[19:28],'RP1':words[28:43],'ROOT':words[43:53]}
        rows=[p.PREFIX+name.encode()+b' '+b' '.join(groups[name]) for name in ('UBUS','LINK','RP1','ROOT')]
        rows.append(p.PREFIX+b'BARS BARS_CALL=5 BARS_RC=0 BARS_STATE=5 BARS_SLOT=5 BARS_TXNS=49 BARS_WRITES=12 BARS_PRESENT=07')
        for i,(original,mask,size,plan) in enumerate(((0x410000,0xffffc000,0x4000,0x410000),(0,0xffc00000,0x400000,0),(0x400000,0xffff0000,0x10000,0x400000),(0,0,0,0),(0,0,0,0),(0,0,0,0))):
            start=0x1f00000000+plan if size else 0;end=start+size
            rows.append((f'RPI5XNU:PCIEID:BAR{i} ORIGINAL={original:08x} MASK={mask:08x} SIZE={size:08x} PLAN={plan:08x} CPU_START={start} CPU_END={end}').encode())
        rows.append(p.PREFIX+b'END '+b' '.join(groups['END']))
        data=data.replace(line,b'\r\n'.join(rows)).replace(b'PCIE_ROOT_ROUTE_TRIAL',b'RP1_BARS_ROOT_TRIAL')
        # Fixture snapshot's BAR0 must equal the saved original in the inventory.
        data=re.sub(rb'RP1_BAR0=[0-9a-f]{8}',b'RP1_BAR0=00410000',data)
        report['boot_markers']=[v.replace('PCIE_ROOT_ROUTE_TRIAL','RP1_BARS_ROOT_TRIAL') for v in report['boot_markers']]
        report['trace_contract']=p.package_source.trace_contract()
        report['bars_contract']=json.loads(json.dumps(p.package_source.bars_contract()))
        report['prior_component_contracts_are_scoped_not_whole_trial']=True
        return data,report

    def test_success_and_precise_nonclaims(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['bars_trial_pass']);self.assertTrue(result['original_bars_restored'])
        self.assertEqual(result['endpoint_config_writes'],12)
        for key in ('ethernet_proven','irq_delivery','dma','bar_assignment_performed','independent_linux_return_proven'):
            self.assertFalse(result[key])

    def test_every_record_required_ordered_and_post_end_fault_rejected(self):
        data,report=self.fixture()
        rows=[row for row in data.splitlines(keepends=True) if row.startswith(p.PREFIX)]
        for row in rows:
            with self.subTest(row=row[:30]),self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        end=rows[-1]
        for marker in p.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete'):p.inspect(data.replace(end,end+marker+b' fixture\r\n'),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(rows[2]+rows[3],rows[3]+rows[2]),report)
        for oldval,newval in ((b'BARS_WRITES=12',b'BARS_WRITES=11'),(b'BARS_TXNS=49',b'BARS_TXNS=48'),
            (b'SIZE=00400000',b'SIZE=00400001'),(b'MASK=ffc00000',b'MASK=ffc00004'),
            (b'PLAN=00410000',b'PLAN=00400000'),(b'BARS_PRESENT=07',b'BARS_PRESENT=03')):
            with self.assertRaises(ValueError):p.inspect(data.replace(oldval,newval),report)

    def test_actual_original_capture_replay_api_uses_raw_framed_bytes(self):
        # Reuse the real full capture-evidence test with this protocol and
        # fixture, preserving offsets/journal/timing from all fourteen rows.
        method=old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        function=types.FunctionType(method.__code__,dict(method.__globals__,p=p))
        function(self)

    def test_failure_keeps_partial_write_uncertainty_and_does_not_commit_sizes(self):
        data,report=self.fixture()
        data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14')
        data=data.replace(b'BARS_CALL=5 BARS_RC=0 BARS_STATE=5',b'BARS_CALL=1 BARS_RC=-4 BARS_STATE=6')
        data=data.replace(b'BARS_TXNS=49 BARS_WRITES=12 BARS_PRESENT=07',b'BARS_TXNS=13 BARS_WRITES=1 BARS_PRESENT=00')
        for i in range(6):
            data=re.sub(p.PREFIX+f'BAR{i} '.encode()+rb'[^\r\n]*',
                p.PREFIX+f'BAR{i} ORIGINAL=00000000 MASK=00000000 SIZE=00000000 PLAN=00000000 CPU_START=0 CPU_END=0'.encode(),data)
        result=p.inspect(data,report)
        self.assertFalse(result['bars_trial_pass']);self.assertFalse(result['original_bars_restored'])
        self.assertEqual(result['endpoint_config_writes'],1)
        changed=copy.deepcopy(report);changed['bars_contract']['command_io_mem_bme_remain_disabled']=1
        with self.assertRaises(ValueError):p.inspect(data,changed)


if __name__=='__main__':unittest.main()
