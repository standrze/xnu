# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import pcie_root_forward_serial_core as p
from tools.rpi5.tests import test_pcie_gem_identify_serial as old
from tools.rpi5.tests import test_pcie_root_route_serial as full


class RootForwardSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.GEMIdentifySerialTests().fixture()
        rows=(b'ROOT_MEM CALL=2 RC=0 STAGE=7 READS=79 WRITES=4 PENDING=0',
            b'ROOT_MEM_COMMAND BEFORE=0400 LIVE=0402 AFTER=0400',
            b'ROOT_MEM_WINDOW BEFORE=0000fff0 WANTED=00400000 LIVE=00400000 AFTER=0000fff0',
            b'ROOT_MEM_CONFIG ID=271214e4 HDR=00010000 BUS=a5010100',
            b'ROOT_MEM_IO OFFSET=0000408c WIDTH=4 WRITE=0 VALUE=0000001e',
            b'ROOT_MEM_OUT0 LO=00000000 HI=00000000 BASELIMIT=fff00000 BASEHI=0000001f LIMITHI=0000001f',
            b'ROOT_MEM_OUT1 LO=00000000 HI=00000004 BASELIMIT=fff00000 BASEHI=0000001c LIMITHI=0000001e')
        data=data.replace(p.PREFIX+b'END ',b'\r\n'.join(p.PREFIX+row for row in rows)+b'\r\n'+p.PREFIX+b'END ')
        data=data.replace(b'PCIE_GEM_IDENTIFY_TRIAL',b'PCIE_ROOT_FORWARD_TRIAL')
        report['boot_markers']=[v.replace('PCIE_GEM_IDENTIFY_TRIAL','PCIE_ROOT_FORWARD_TRIAL') for v in report['boot_markers']]
        report['marker']=report['marker'].replace('PCIE_GEM_IDENTIFY_TRIAL','PCIE_ROOT_FORWARD_TRIAL')
        report.update(root_forward_contract=p.package_source.root_forward_contract(),gem_contract=p.package_source.gem_contract(),
            decode_contract=p.package_source.decode_contract(),owner_trace=p.package_source.owner_contract(),trace_contract=p.package_source.trace_contract())
        return data,report

    def test_exact_success_preserves_status_and_original_nonidentical_window(self):
        data,report=self.fixture();r=p.inspect(data,report)
        self.assertTrue(r['root_forward_trial_pass']);self.assertTrue(r['root_memory_forwarding_restored'])
        self.assertTrue(r['gem_identification_proven']);self.assertTrue(r['mappings_revoked']);self.assertTrue(r['original_bars_restored'])
        self.assertEqual(r['observed_field_rows'],42);self.assertEqual(r['root_config_writes_attempted'],4)
        self.assertFalse(r['ethernet_proven']);self.assertFalse(r['dma']);self.assertFalse(r['irq_delivery'])
        for before,after in ((b'ROOT_MEM CALL=2',b'ROOT_MEM CALL=1'),(b'STAGE=7 READS=79',b'STAGE=8 READS=79'),
            (b'READS=79 WRITES=4',b'READS=78 WRITES=4'),(b'WRITES=4 PENDING=0',b'WRITES=4 PENDING=1'),
            (b'BEFORE=0400',b'BEFORE=0404'),(b'LIVE=0402',b'LIVE=0406'),(b'AFTER=0400',b'AFTER=0000'),
            (b'BEFORE=0000fff0',b'BEFORE=0000fff1'),(b'WANTED=00400000',b'WANTED=00300000'),
            (b'LIVE=00400000',b'LIVE=00500000'),(b'AFTER=0000fff0',b'AFTER=00400000'),
            (b'ID=271214e4',b'ID=271114e4'),(b'HDR=00010000',b'HDR=00000000'),(b'BUS=a5010100',b'BUS=a5000000'),
            (b'WIDTH=4 WRITE=0',b'WIDTH=2 WRITE=0'),(b'BASELIMIT=fff00000',b'BASELIMIT=fff00010'),
            (b'ROOT_MEM_OUT1 LO=00000000 HI=00000004',b'ROOT_MEM_OUT1 LO=00000000 HI=00000003'),
            (b'VALUE=0000001e',b'VALUE=0000001c')):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after),report)

    def test_full_original_health_order_and_contract(self):
        data,report=self.fixture()
        rows=[row for row in data.splitlines(keepends=True) if row.startswith(p.PREFIX+b'ROOT_MEM')]
        self.assertEqual(len(rows),7)
        for row in rows:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):
                p.inspect(data.replace(row,row.rstrip()+b' panic(cpu fixture\r\n'),report)
        for signature in p.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):p.inspect(data+signature+b' after END\r\n',report)
        with self.assertRaises(ValueError):p.inspect(data.replace(rows[0]+rows[1],rows[1]+rows[0]),report)
        changed=copy.deepcopy(report);changed['root_forward_contract']['root_command_changed_bits']=6
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_original_complete_capture_api(self):
        method=full.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_partial_failure_leaves_forwarding_unknown_not_restored(self):
        data,report=self.fixture();data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14')
        data=data.replace(b'BARS_PRESENT=07',b'BARS_PRESENT=00')
        for i in range(6):
            data=re.sub(p.PREFIX+f'BAR{i} '.encode()+rb'[^\r\n]*',p.PREFIX+f'BAR{i} ORIGINAL=00000000 MASK=00000000 SIZE=00000000 PLAN=00000000 CPU_START=0 CPU_END=0'.encode(),data)
        data=data.replace(b'ASSIGN CALL=6 RC=0 STATE=6 SLOT=2 TXNS=58 WRITES=6 ASSIGNED=07 RESTORED=07',
            b'ASSIGN CALL=3 RC=0 STATE=4 SLOT=2 TXNS=29 WRITES=3 ASSIGNED=07 RESTORED=00')
        for name in ('ASSIGNED_BARS','RESTORED_BARS'):
            data=re.sub(p.PREFIX+name.encode()+rb'[^\r\n]*',p.PREFIX+name.encode()+b' '+b' '.join(f'BAR{i}=00000000'.encode() for i in range(6)),data)
        data=re.sub(p.PREFIX+rb'MAPPING [^\r\n]*',p.PREFIX+b'MAPPING BAR1_START=0 BAR1_END=0 GEM_START=0 GEM_END=0 CLOCK_START=0 CLOCK_END=0',data)
        data=data.replace(b'DECODE CALL=3 RC=0 STATE=8 TXNS=34 WRITES=2 MAPPED=03 UNMAPPED=03',
            b'DECODE CALL=1 RC=-5 STATE=9 TXNS=22 WRITES=1 MAPPED=03 UNMAPPED=00').replace(b'ENABLED=0002',b'ENABLED=0000')
        data=data.replace(b'GEM CALL=2 RC=0 STAGE=5 READS=32 READY=1',b'GEM CALL=1 RC=-5 STAGE=6 READS=15 READY=0')
        data=data.replace(b'COMMITTED=00070106 HZ=200000000',b'COMMITTED=00000000 HZ=0')
        data=data.replace(b'ROOT_MEM CALL=2 RC=0 STAGE=7 READS=79 WRITES=4',b'ROOT_MEM CALL=1 RC=-5 STAGE=8 READS=47 WRITES=2')
        data=data.replace(b'AFTER=0400',b'AFTER=0000').replace(b'AFTER=0000fff0',b'AFTER=00000000')
        r=p.inspect(data,report);self.assertFalse(r['root_forward_trial_pass']);self.assertFalse(r['root_memory_forwarding_restored'])
        self.assertIsNone(r['root_memory_forwarding_enabled']);self.assertTrue(r['root_memory_forwarding_attempted'])
        self.assertFalse(r['mappings_revoked']);self.assertFalse(r['original_command_restored']);self.assertFalse(r['original_bars_restored'])
        self.assertEqual(r['root_config_reads_attempted'],47)


if __name__=='__main__':unittest.main()
