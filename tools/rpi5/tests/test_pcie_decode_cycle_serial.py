# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import pcie_decode_cycle_serial_core as p
from tools.rpi5.tests import test_pcie_bars_assignment_serial as old


class DecodeCycleSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.BarsAssignmentSerialTests().fixture()
        rows=[b'DECODE CALL=3 RC=0 STATE=8 TXNS=34 WRITES=2 MAPPED=03 UNMAPPED=03',
            b'DECODE_COMMAND BEFORE=0000 ENABLED=0002 AFTER=0000']
        data=data.replace(p.PREFIX+b'END ',b'\r\n'.join(p.PREFIX+row for row in rows)+b'\r\n'+p.PREFIX+b'END ')
        data=data.replace(b'PCIE_BARS_ASSIGNMENT_TRIAL',b'PCIE_DECODE_CYCLE_TRIAL')
        anchor=report['boot_markers'][0].replace('PCIE_BARS_ASSIGNMENT_TRIAL','PCIE_DECODE_CYCLE_TRIAL').encode()
        report['boot_markers']=p.package_source.configured_source().configured_builder().boot_markers('f'*32)
        data=data.replace(anchor,b'\r\n'.join(v.encode() for v in report['boot_markers']))
        report['marker']=next(v for v in report['boot_markers'] if v.startswith('RPI5XNU:BL33:PCIE_DECODE_CYCLE_TRIAL TAG='))
        report.update(decode_contract=p.package_source.decode_contract(),owner_trace=p.package_source.owner_contract(),trace_contract=p.package_source.trace_contract())
        return data,report

    def test_exact_success_and_no_nic_dma_or_irq_claim(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['decode_cycle_trial_pass']);self.assertTrue(result['original_bars_restored'])
        self.assertTrue(result['mappings_revoked']);self.assertTrue(result['original_command_restored'])
        self.assertEqual(result['observed_field_rows'],25);self.assertEqual(result['endpoint_config_writes'],20)
        for name in ('memory_decode_enabled','endpoint_register_access','ethernet_proven','dma','irq_delivery'):
            self.assertFalse(result[name])
        for a,b in ((b'DECODE CALL=3',b'DECODE CALL=2'),(b'STATE=8 TXNS=34',b'STATE=7 TXNS=34'),
            (b'TXNS=34 WRITES=2',b'TXNS=33 WRITES=2'),(b'MAPPED=03 UNMAPPED=03',b'MAPPED=03 UNMAPPED=01'),
            (b'ENABLED=0002',b'ENABLED=0006'),(b'AFTER=0000',b'AFTER=0002'),
            (b'RESTORED_BARS BAR0=ffffc000',b'RESTORED_BARS BAR0=00410000')):
            with self.assertRaises(ValueError):p.inspect(data.replace(a,b),report)

    def test_raw_health_order_and_exact_contract(self):
        data,report=self.fixture()
        rows=[row for row in data.splitlines(keepends=True) if any(row.startswith(p.PREFIX+name.encode()+b' ') for name in p.ADDITIONS)]
        self.assertEqual(len(rows),2)
        for row in rows:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):
                p.inspect(data.replace(row,row.rstrip()+b' panic(cpu fixture\r\n'),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(rows[0]+rows[1],rows[1]+rows[0]),report)
        for signature in p.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):p.inspect(data+signature+b' fixture\n',report)
        changed=copy.deepcopy(report);changed['decode_contract']['command_changed_bits']=6
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_original_complete_capture_api(self):
        method=old.old.old.old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_partial_decode_failure_never_means_cleanup(self):
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
            b'DECODE CALL=1 RC=-4 STATE=9 TXNS=22 WRITES=1 MAPPED=01 UNMAPPED=00')
        data=data.replace(b'ENABLED=0002',b'ENABLED=0000')
        result=p.inspect(data,report)
        self.assertFalse(result['decode_cycle_trial_pass']);self.assertFalse(result['original_bars_restored'])
        self.assertFalse(result['original_command_restored']);self.assertIsNone(result['memory_decode_enabled'])
        self.assertTrue(result['memory_decode_attempted'])


if __name__=='__main__':unittest.main()
