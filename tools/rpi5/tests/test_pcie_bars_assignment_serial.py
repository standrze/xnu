# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import pcie_bars_assignment_serial_core as p
from tools.rpi5.tests import test_pcie_guard_composition_serial as old


class BarsAssignmentSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.GuardCompositionSerialTests().fixture()
        # Match the board's actual saved originals, deliberately distinct from
        # every implemented BAR's pure assignment plan.
        for i,value in enumerate((0xffffc000,0xffc00000,0xffff0000)):
            data=re.sub(p.PREFIX+f'BAR{i} ORIGINAL='.encode()+rb'[0-9a-f]{8}',
                p.PREFIX+f'BAR{i} ORIGINAL={value:08x}'.encode(),data)
        data=re.sub(rb'RP1_BAR0=[0-9a-f]{8}',b'RP1_BAR0=ffffc000',data)
        data=re.sub(rb'(?<![A-Z_])BAR1=[0-9a-f]{8}',b'BAR1=ffc00000',data)
        data=re.sub(rb'RP1_BAR1=[0-9a-f]{8}',b'RP1_BAR1=ffc00000',data)
        rows=[b'ASSIGN CALL=6 RC=0 STATE=6 SLOT=2 TXNS=58 WRITES=6 ASSIGNED=07 RESTORED=07',
            b'ASSIGNED_BARS BAR0=00410000 BAR1=00000000 BAR2=00400000 BAR3=00000000 BAR4=00000000 BAR5=00000000',
            b'RESTORED_BARS BAR0=ffffc000 BAR1=ffc00000 BAR2=ffff0000 BAR3=00000000 BAR4=00000000 BAR5=00000000',
            f'MAPPING BAR1_START={0x1f00000000} BAR1_END={0x1f00400000} GEM_START={0x1f00100000} GEM_END={0x1f00104000} CLOCK_START={0x1f00018000} CLOCK_END={0x1f0002c000}'.encode()]
        data=data.replace(p.PREFIX+b'END ',b'\r\n'.join(p.PREFIX+row for row in rows)+b'\r\n'+p.PREFIX+b'END ')
        data=data.replace(b'PCIE_GUARD_COMPOSITION_TRIAL',b'PCIE_BARS_ASSIGNMENT_TRIAL')
        report['boot_markers']=[v.replace('PCIE_GUARD_COMPOSITION_TRIAL','PCIE_BARS_ASSIGNMENT_TRIAL') for v in report['boot_markers']]
        report['marker']=next(v for v in report['boot_markers'] if v.startswith('RPI5XNU:BL33:PCIE_BARS_ASSIGNMENT_TRIAL TAG='))
        report.update(assignment_contract=p.package_source.assignment_contract(),owner_trace=p.package_source.owner_contract(),
            guard_composition=p.package_source.guard_contract(),trace_contract=p.package_source.trace_contract())
        return data,report

    def test_exact_success_with_no_mapping_decode_or_ethernet_claim(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['assignment_trial_pass']);self.assertTrue(result['exact_assignment_and_restore_proven'])
        self.assertEqual(result['observed_field_rows'],23);self.assertEqual(result['endpoint_config_writes'],18)
        self.assertEqual([result['restored_bars'][f'bar{i}'] for i in range(3)],[0xffffc000,0xffc00000,0xffff0000])
        self.assertEqual([result['assigned_bars'][f'bar{i}'] for i in range(3)],[0x410000,0,0x400000])
        for name in ('mapping_performed','memory_decode_enabled','ethernet_proven','dma','irq_delivery'):
            self.assertFalse(result[name])
        for before,after in ((b'STATE=6 SLOT=2',b'STATE=4 SLOT=2'),(b'TXNS=58 WRITES=6',b'TXNS=57 WRITES=6'),
            (b'ASSIGNED=07 RESTORED=07',b'ASSIGNED=07 RESTORED=03'),(b'ASSIGNED_BARS BAR0=00410000',b'ASSIGNED_BARS BAR0=00400000'),
            (b'RESTORED_BARS BAR0=ffffc000',b'RESTORED_BARS BAR0=00410000'),
            (str(0x1f00104000).encode(),str(0x1f00108000).encode()),(b'COMMAND=0000',b'COMMAND=0002')):
            with self.assertRaises(ValueError):p.inspect(data.replace(before,after),report)
        assigned=next(row for row in data.splitlines() if row.startswith(p.PREFIX+b'ASSIGNED_BARS '))
        restored=next(row for row in data.splitlines() if row.startswith(p.PREFIX+b'RESTORED_BARS '))
        swapped=data.replace(assigned,restored.replace(b'RESTORED_BARS ',b'ASSIGNED_BARS ')).replace(restored,assigned.replace(b'ASSIGNED_BARS ',b'RESTORED_BARS '))
        with self.assertRaisesRegex(ValueError,'Assignment/restoration differs'):p.inspect(swapped,report)

    def test_all_records_and_original_whole_capture_health(self):
        data,report=self.fixture()
        rows=[row for row in data.splitlines(keepends=True) if any(row.startswith(p.PREFIX+label.encode()+b' ') for label in p.ADDITIONS)]
        self.assertEqual(len(rows),4)
        for row in rows:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):
                p.inspect(data.replace(row,row.rstrip()+b' panic(cpu fixture\r\n'),report)
        for marker in p.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete original'):p.inspect(data+marker+b' fixture\n',report)
        with self.assertRaises(ValueError):p.inspect(data.replace(rows[0]+rows[1],rows[1]+rows[0]),report)
        changed=copy.deepcopy(report);changed['assignment_contract']['command_writes']=1
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_original_complete_capture_api(self):
        method=old.old.old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_partial_assignment_failure_is_not_restoration(self):
        data,report=self.fixture();data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14')
        data=data.replace(b'BARS_PRESENT=07',b'BARS_PRESENT=00')
        for i in range(6):
            data=re.sub(p.PREFIX+f'BAR{i} '.encode()+rb'[^\r\n]*',p.PREFIX+f'BAR{i} ORIGINAL=00000000 MASK=00000000 SIZE=00000000 PLAN=00000000 CPU_START=0 CPU_END=0'.encode(),data)
        data=data.replace(b'ASSIGN CALL=6 RC=0 STATE=6 SLOT=2 TXNS=58 WRITES=6 ASSIGNED=07 RESTORED=07',
            b'ASSIGN CALL=4 RC=-4 STATE=7 SLOT=1 TXNS=43 WRITES=5 ASSIGNED=07 RESTORED=01')
        for name in ('ASSIGNED_BARS','RESTORED_BARS'):
            data=re.sub(p.PREFIX+name.encode()+rb'[^\r\n]*',p.PREFIX+name.encode()+b' '+b' '.join(f'BAR{i}=00000000'.encode() for i in range(6)),data)
        data=re.sub(p.PREFIX+rb'MAPPING [^\r\n]*',p.PREFIX+b'MAPPING BAR1_START=0 BAR1_END=0 GEM_START=0 GEM_END=0 CLOCK_START=0 CLOCK_END=0',data)
        result=p.inspect(data,report)
        self.assertFalse(result['assignment_trial_pass']);self.assertFalse(result['original_bars_restored'])
        self.assertTrue(result['assignment_attempted']);self.assertEqual(result['assignment_telemetry']['writes'],5)
        self.assertFalse(result['exact_assignment_and_restore_proven'])


if __name__=='__main__':unittest.main()
