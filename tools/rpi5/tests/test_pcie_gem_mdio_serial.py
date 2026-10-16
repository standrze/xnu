# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_gem_mdio_serial_core as p
from tools.rpi5.tests import test_pcie_gem_capabilities_serial as prior
from tools.rpi5.tests import test_pcie_root_forward_serial as full


class GEMMDIOSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=prior.GEMCapabilitiesSerialTests().fixture()
        data=data.replace(b'PCIE_GEM_CAPABILITIES_TRIAL',b'PCIE_GEM_MDIO_TRIAL').replace(b'00070106',b'00070109')
        caps=[0x70109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0]
        for side in ('BEFORE','AFTER'):
            for half,labels in enumerate(('MID DCFG1 DCFG2 DCFG5','DCFG6 DCFG8 DCFG10 DCFG12')):
                prefix=p.PREFIX+('CAP_'+side+str(half)+' ').encode()
                row=prefix+b' '.join(('%s=%08x'%(name,value)).encode() for name,value in zip(labels.split(),caps[half*4:half*4+4]))
                data=re.sub(prefix+rb'[^\r\n]+',lambda unused:row,data)
        rows=[
            b'MDIO STATE=2 STAGE=7 RC=0 PHY=1 TRANSFERS=5',
            b'MDIO_IO READS=26 WRITES=9 POLLS=12 CLOCKS=37 CLK_CHANGED=1',
            b'MDIO_NCR BEFORE=00000000 LIVE=00000010 AFTER=00000000',
            b'MDIO_CFG BEFORE=00000000 LIVE=00140000 AFTER=00000000',
            b'MDIO_PHY ID1=600d ID2=84a2 BMCR=1140 BMSR_FIRST=7909 BMSR_NOW=792d',
            b'MDIO_TIME START_US=100 LAST_US=200 DEADLINE_US=20100']
        data=data.replace(p.PREFIX+b'END ',b'\n'.join(p.PREFIX+row for row in rows)+b'\n'+p.PREFIX+b'END ')
        report['marker']=report['marker'].replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_GEM_MDIO_TRIAL')
        report['boot_markers']=[s.replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_GEM_MDIO_TRIAL') for s in report['boot_markers']]
        for name,factory in (('mdio_contract','mdio_contract'),('root_forward_contract','root_forward_contract'),
            ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
            report[name]=getattr(p.package_source,factory)()
        return data,report

    def test_exact_success_restoration_counts_and_field_negatives(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['mdio_trial_pass']);self.assertTrue(result['management_config_restored'])
        self.assertEqual(result['observed_field_rows'],53);self.assertEqual(result['endpoint_register_reads_completed'],74)
        self.assertEqual(result['phy_observation']['phy_id'],0x600d84a2)
        self.assertFalse(result['phy_register_writes']);self.assertFalse(result['ethernet_proven'])
        changes=((b'MDIO STATE=2',b'MDIO STATE=3'),(b'STAGE=7 RC=0 PHY=1',b'STAGE=7 RC=0 PHY=2'),
            (b'MDIO_IO READS=26',b'MDIO_IO READS=25'),(b'WRITES=9 POLLS=12',b'WRITES=10 POLLS=12'),
            (b'CLOCKS=37 CLK_CHANGED=1',b'CLOCKS=36 CLK_CHANGED=1'),
            (b'LIVE=00000010 AFTER=00000000',b'LIVE=00000014 AFTER=00000000'),
            (b'LIVE=00140000 AFTER=00000000',b'LIVE=00140000 AFTER=00140000'),
            (b'LIVE=00140000',b'LIVE=00100000'),(b'BMCR=1140',b'BMCR=ffff'),
            (b'ID1=600d ID2=84a2',b'ID1=ffff ID2=ffff'),
            (b'LAST_US=200',b'LAST_US=99'),(b'DEADLINE_US=20100',b'DEADLINE_US=20101'))
        for before,after in changes:
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        changed=copy.deepcopy(report);changed['mdio_contract']['phy_address']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)
        # An already safe divisor has fewer operations, but is restored exactly.
        safe=data.replace(b'READS=26 WRITES=9 POLLS=12 CLOCKS=37 CLK_CHANGED=1',b'READS=25 WRITES=7 POLLS=12 CLOCKS=34 CLK_CHANGED=0')
        safe=safe.replace(b'MDIO_CFG BEFORE=00000000 LIVE=00140000 AFTER=00000000',b'MDIO_CFG BEFORE=00180000 LIVE=00180000 AFTER=00180000')
        self.assertTrue(p.inspect(safe,report)['mdio_trial_pass'])
        down=data.replace(b'BMSR_NOW=792d',b'BMSR_NOW=7909')
        self.assertEqual(p.inspect(down,report)['phy_observation']['link'],0)
        for upper in range(8):
            identity=(upper<<29)|0x1fffffff
            raw=data.replace(b'ID1=600d ID2=84a2',('ID1=%04x ID2=%04x'%(identity>>16,identity&0xffff)).encode())
            with self.subTest(invalid_id=identity),self.assertRaises(ValueError):p.inspect(raw,report)

    def test_actual_full_recorder_api_and_entire_raw_fault_tail(self):
        method=full.RootForwardSerialTests.test_actual_original_complete_capture_api
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)
        data,report=self.fixture()
        for value in (b'panic(cpu 0 caller 0x1): failure\n',b'RPI5XNU:FAULT\n'):
            for offset in (0,data.index(p.PREFIX+b'END '),len(data)):
                with self.assertRaises(ValueError):p.inspect(data[:offset]+value+data[offset:],report)

    def test_partial_failure_preserves_live_unknown_not_restored(self):
        data,report=self.fixture()
        data=data.replace(b'MDIO STATE=2 STAGE=7 RC=0 PHY=1 TRANSFERS=5',b'MDIO STATE=3 STAGE=4 RC=-5 PHY=1 TRANSFERS=2')
        observed=[]
        def inspect(raw,metadata):
            result=p.inspect(raw,metadata);observed.append(result);return result
        proxy=types.SimpleNamespace(**vars(p));proxy.inspect=inspect
        method=full.RootForwardSerialTests.test_partial_failure_leaves_forwarding_unknown_not_restored
        # Preserve the original failure construction while updating its exact
        # synthetic MID constant to this new, independently selected profile.
        old=b'COMMITTED=00070106 HZ=200000000';new=b'COMMITTED=00070109 HZ=200000000'
        self.assertEqual(method.__code__.co_consts.count(old),1)
        code=method.__code__.replace(co_consts=tuple(new if v==old else v for v in method.__code__.co_consts))
        with patch.object(self,'fixture',lambda:(data,report)):
            types.FunctionType(code,dict(method.__globals__,p=proxy))(self)
        result=observed[0];self.assertFalse(result['mdio_trial_pass']);self.assertFalse(result['management_config_restored'])
        self.assertIsNone(result['phy_observation']);self.assertIsNone(result['endpoint_register_reads_completed'])


if __name__=='__main__':unittest.main()
