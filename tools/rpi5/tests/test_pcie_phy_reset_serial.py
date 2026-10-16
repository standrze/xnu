# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_phy_reset_serial_core as p
from tools.rpi5.tests import test_pcie_gem_mdio_serial as prior
from tools.rpi5.tests import test_pcie_root_forward_serial as full


class PHYResetSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=prior.GEMMDIOSerialTests().fixture()
        old=p.prior.prior.package_source.DEVICE_MARKER;new=p.package_source.DEVICE_MARKER
        data=data.replace(b'PCIE_GEM_MDIO_TRIAL',b'PCIE_PHY_RESET_TRIAL').replace(old.encode(),new.encode())
        data=data.replace(b'CLOCKS=37 CLK_CHANGED=1',b'CLOCKS=2 CLK_CHANGED=1')
        data=data.replace(b'MDIO_TIME START_US=100 LAST_US=200 DEADLINE_US=20100',
            b'MDIO_TIME START_US=6100 LAST_US=6200 DEADLINE_US=26100')
        rows=[b'PHYRESET STATE=2 RC=0 STEP=8 READS=19 WRITES=12 PENDING=0',
            b'PHYRESET_MAP STATE=2 RC=0 MAPPED=7 UNMAPPED=7 LINK_CONTROL=0000',
            b'PHYRESET_CTRL BEFORE=0000009f AFTER=0000009f PAD_BEFORE=000000d6 PAD_AFTER=000000d6',
            b'PHYRESET_RIO OUT_BEFORE=00000001 OUT_AFTER=00000001 OE_BEFORE=00000001 OE_AFTER=00000001',
            b'PHYRESET_INPUT LOW=00000003 HIGH=00000013 PCIE_INTE=00000000',
            b'PHYRESET_TIME START_US=100 LAST_US=6300 DEADLINE_US=40100 ASSERTED_US=1000 DEASSERTED_US=6100 COMPLETED_US=6300']
        data=data.replace(p.PREFIX+b'END ',b'\n'.join(p.PREFIX+row for row in rows)+b'\n'+p.PREFIX+b'END ')
        report['marker']=report['marker'].replace('PCIE_GEM_MDIO_TRIAL','PCIE_PHY_RESET_TRIAL')
        report['boot_markers']=[s.replace('PCIE_GEM_MDIO_TRIAL','PCIE_PHY_RESET_TRIAL').replace(old,new) for s in report['boot_markers']]
        report.pop('mdio_contract',None)
        for name,factory in (('reset_contract','reset_contract'),('root_forward_contract','root_forward_contract'),
            ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),
            ('trace_contract','trace_contract'),('rp1_device_handoff','gpio_handoff_contract')):
            report[name]=getattr(p.package_source,factory)()
        return data,report

    def test_exact_success_and_reset_deadline_field_negatives(self):
        data,report=self.fixture();got=p.inspect(data,report)
        self.assertTrue(got['phy_reset_trial_pass']);self.assertTrue(got['gpio_original_fields_restored'])
        self.assertEqual(got['endpoint_register_reads_completed'],93);self.assertEqual(got['endpoint_register_writes_attempted'],21)
        self.assertFalse(got['ethernet_proven']);self.assertFalse(got['phy_reset_cause_of_prior_floating_reads_proven'])
        changes=((b'PHYRESET STATE=2',b'PHYRESET STATE=3'),(b'READS=19 WRITES=12',b'READS=19 WRITES=11'),
            (b'MAPPED=7 UNMAPPED=7',b'MAPPED=7 UNMAPPED=0'),(b'LINK_CONTROL=0000',b'LINK_CONTROL=0001'),
            (b'BEFORE=0000009f AFTER=0000009f',b'BEFORE=0000009f AFTER=0000001f'),
            (b'PAD_AFTER=000000d6',b'PAD_AFTER=00000056'),(b'OE_AFTER=00000001',b'OE_AFTER=00000011'),
            (b'LOW=00000003 HIGH=00000013',b'LOW=00000013 HIGH=00000013'),(b'PCIE_INTE=00000000',b'PCIE_INTE=00000010'),
            (b'DEASSERTED_US=6100',b'DEASSERTED_US=5999'),(b'DEADLINE_US=40100',b'DEADLINE_US=40101'),
            (b'CLOCKS=2 CLK_CHANGED=1',b'CLOCKS=37 CLK_CHANGED=1'),(b'ID1=600d ID2=84a2',b'ID1=ffff ID2=ffff'))
        for old,new in changes:
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        changed=copy.deepcopy(report);changed['reset_contract']['gpio_write_limit']=12.0
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_full_recorder_api_and_entire_raw_fault_tail(self):
        method=full.RootForwardSerialTests.test_actual_original_complete_capture_api
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)
        data,report=self.fixture()
        for value in (b'panic(cpu 0 caller 0x1): failure\n',b'RPI5XNU:FAULT\n'):
            for offset in (0,data.index(p.PREFIX+b'END '),len(data)):
                with self.assertRaises(ValueError):p.inspect(data[:offset]+value+data[offset:],report)

    def test_propagated_minus6_is_retained_failure_not_rehabilitation(self):
        data,report=self.fixture()
        data=data.replace(b'PHYRESET STATE=2 RC=0 STEP=8 READS=19 WRITES=12',
            b'PHYRESET STATE=3 RC=-6 STEP=6 READS=14 WRITES=7')
        data=data.replace(b'PHYRESET_MAP STATE=2 RC=0 MAPPED=7 UNMAPPED=7',
            b'PHYRESET_MAP STATE=3 RC=-6 MAPPED=7 UNMAPPED=0')
        data=data.replace(b'MDIO STATE=2 STAGE=7 RC=0',b'MDIO STATE=3 STAGE=7 RC=-6')
        data=data.replace(b'ID1=600d ID2=84a2 BMCR=1140 BMSR_FIRST=7909 BMSR_NOW=792d',
            b'ID1=ffff ID2=ffff BMCR=ffff BMSR_FIRST=ffff BMSR_NOW=ffff')
        observed=[]
        def inspect(raw,metadata):
            raw=raw.replace(b'RC=-5',b'RC=-6');result=p.inspect(raw,metadata);observed.append((raw,result));return result
        proxy=types.SimpleNamespace(**vars(p));proxy.inspect=inspect
        method=full.RootForwardSerialTests.test_partial_failure_leaves_forwarding_unknown_not_restored
        old=b'COMMITTED=00070106 HZ=200000000';new=b'COMMITTED=00070109 HZ=200000000'
        code=method.__code__.replace(co_consts=tuple(new if v==old else v for v in method.__code__.co_consts))
        with patch.object(self,'fixture',lambda:(data,report)):
            types.FunctionType(code,dict(method.__globals__,p=proxy))(self)
        raw,result=observed[0];self.assertFalse(result['phy_reset_trial_pass']);self.assertFalse(result['gpio_original_fields_restored'])
        self.assertEqual([result['root_forward_progress']['rc'],result['gem_progress']['rc'],result['decode_telemetry']['rc']],[-6]*3)
        self.assertIsNone(result['phy_observation']);self.assertIsNone(result['endpoint_register_reads_completed'])
        # The live link/ASPM action precondition can refuse before the reset
        # core has entered; retain that diagnostic failure without fabricating
        # a child error or claiming it measured an electrical reset condition.
        unentered=raw.replace(b'PHYRESET STATE=3 RC=-6 STEP=6 READS=14 WRITES=7 PENDING=0',
            b'PHYRESET STATE=0 RC=0 STEP=0 READS=0 WRITES=0 PENDING=0')
        got=p.inspect(unentered,report);self.assertFalse(got['phy_reset_trial_pass'])
        self.assertTrue(got['reset_action_refused_before_core_entry'])
        with self.assertRaises(ValueError):p.inspect(raw.replace(b'RC=-6',b'RC=-7'),report)


if __name__=='__main__':unittest.main()
