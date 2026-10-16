# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import pcie_gem_identify_serial_core as p
from tools.rpi5.tests import test_pcie_decode_cycle_serial as old


class GEMIdentifySerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.DecodeCycleSerialTests().fixture()
        rows=[b'GEM CALL=2 RC=0 STAGE=5 READS=32 READY=1 INDEX=1 OFFSET=00008014']
        for side in ('BEFORE','AFTER'):
            for n,fields in enumerate(('CTRL=00000802 DIV=00000001 SEL=00000004 CS=80000001',
                'PWR=00000004 INT=00000014 FRAC=00000000 PRIM=00051000',
                'ETH_CTRL=00000800 ETH_DIV=00000001 ETH_SEL=00000002 TSU_CTRL=00000800',
                'TSU_DIV=00000001 TSU_SEL=00000002 SEC=80000800')):
                rows.append(f'CLOCK_{side}{n} {fields}'.encode())
        rows.append(b'GEM_MID FIRST=00070106 SECOND=00070106 COMMITTED=00070106 HZ=200000000')
        data=data.replace(p.PREFIX+b'END ',b'\r\n'.join(p.PREFIX+row for row in rows)+b'\r\n'+p.PREFIX+b'END ')
        data=data.replace(b'PCIE_DECODE_CYCLE_TRIAL',b'PCIE_GEM_IDENTIFY_TRIAL')
        report['boot_markers']=[v.replace('PCIE_DECODE_CYCLE_TRIAL','PCIE_GEM_IDENTIFY_TRIAL') for v in report['boot_markers']]
        report['marker']=report['marker'].replace('PCIE_DECODE_CYCLE_TRIAL','PCIE_GEM_IDENTIFY_TRIAL')
        report.update(gem_contract=p.package_source.gem_contract(),decode_contract=p.package_source.decode_contract(),
            owner_trace=p.package_source.owner_contract(),trace_contract=p.package_source.trace_contract())
        return data,report

    def test_complete_exact_success_no_packet_or_dma_claim(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['gem_identify_trial_pass']);self.assertTrue(result['original_bars_restored'])
        self.assertTrue(result['mappings_revoked']);self.assertTrue(result['original_command_restored'])
        self.assertEqual(result['observed_field_rows'],35);self.assertEqual(result['endpoint_register_reads_completed'],32)
        for name in ('ethernet_proven','dma','irq_delivery','clock_reset_writes'):self.assertFalse(result[name])
        for a,b in ((b'GEM CALL=2',b'GEM CALL=1'),(b'STAGE=5 READS=32',b'STAGE=6 READS=32'),
            (b'READS=32 READY=1',b'READS=31 READY=1'),(b'READY=1 INDEX=1',b'READY=0 INDEX=1'),
            (b'CS=80000001',b'CS=80000101'),(b'PWR=00000004',b'PWR=00000104'),
            (b'ETH_SEL=00000002',b'ETH_SEL=00000003'),(b'ETH_CTRL=00000800',b'ETH_CTRL=00000820'),
            (b'SEC=80000800',b'SEC=80010800'),(b'TSU_DIV=00000001',b'TSU_DIV=00000002'),
            (b'SECOND=00070106',b'SECOND=00070107'),(b'HZ=200000000',b'HZ=199999999')):
            with self.subTest(a=a),self.assertRaises(ValueError):p.inspect(data.replace(a,b),report)
        for stage in (b'CLOCK_BEFORE',b'CLOCK_AFTER'):
            changed=data.replace(stage+b'0 CTRL=00000802',stage+b'0 CTRL=00001802')
            with self.assertRaisesRegex(ValueError,'Stable known clock'):p.inspect(changed,report)

    def test_full_raw_faults_order_and_contract(self):
        data,report=self.fixture()
        rows=[v for v in data.splitlines(keepends=True) if any(v.startswith(p.PREFIX+n.encode()+b' ') for n in p.ADDITIONS)]
        self.assertEqual(len(rows),10)
        for row in rows:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):
                p.inspect(data.replace(row,row.rstrip()+b' panic(cpu fixture\r\n'),report)
        for signature in p.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):p.inspect(data+signature+b' after END\r\n',report)
        changed=copy.deepcopy(report);changed['gem_contract']['endpoint_register_writes']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_full_inspect_capture_api(self):
        method=old.old.old.old.old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_partial_clock_failure_preserves_failure_and_no_cleanup_claim(self):
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
            b'DECODE CALL=1 RC=-5 STATE=9 TXNS=22 WRITES=1 MAPPED=03 UNMAPPED=00')
        data=data.replace(b'ENABLED=0002',b'ENABLED=0000')
        data=data.replace(b'GEM CALL=2 RC=0 STAGE=5 READS=32 READY=1',b'GEM CALL=1 RC=-5 STAGE=6 READS=15 READY=0')
        data=data.replace(b'COMMITTED=00070106 HZ=200000000',b'COMMITTED=00000000 HZ=0')
        result=p.inspect(data,report);self.assertFalse(result['gem_identify_trial_pass'])
        self.assertFalse(result['mappings_revoked']);self.assertFalse(result['original_command_restored'])
        self.assertIsNone(result['endpoint_register_reads_completed']);self.assertEqual(result['endpoint_register_reads_attempted'],15)


if __name__=='__main__':unittest.main()
