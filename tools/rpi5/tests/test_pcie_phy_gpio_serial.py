# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_phy_gpio_serial_core as p
from tools.rpi5.tests import test_pcie_gem_capabilities_serial as prior
from tools.rpi5.tests import test_pcie_root_forward_serial as full


class PHYGPIOObserveSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=prior.GEMCapabilitiesSerialTests().fixture()
        old=p.prior.package_source.DEVICE_MARKER;new=p.package_source.DEVICE_MARKER
        data=data.replace(b'PCIE_GEM_CAPABILITIES_TRIAL',b'PCIE_PHY_GPIO_TRIAL').replace(b'00070106',b'00070109')
        data=data.replace(old.encode(),new.encode())
        rows=[b'GPIO STATE=2 RC=0 READS=12 MAPPED=7 UNMAPPED=7 INDEX=0',
            b'GPIO_PROGRESS PASS=1 WORD=5 PENDING=0',
            b'GPIO0_CTRL STATUS=00032200 CTRL=00000005 PAD=00000056',
            b'GPIO0_RIO OUT=00000010 OE=00000010 IN=00000010',
            b'GPIO1_CTRL STATUS=00032200 CTRL=00000005 PAD=00000056',
            b'GPIO1_RIO OUT=00000010 OE=00000010 IN=00000010']
        data=data.replace(p.PREFIX+b'END ',b'\n'.join(p.PREFIX+row for row in rows)+b'\n'+p.PREFIX+b'END ')
        report['marker']=report['marker'].replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_PHY_GPIO_TRIAL')
        report['boot_markers']=[s.replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_PHY_GPIO_TRIAL').replace(old,new) for s in report['boot_markers']]
        for name,factory in (('gpio_contract','gpio_contract'),('root_forward_contract','root_forward_contract'),
            ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),
            ('trace_contract','trace_contract'),('rp1_device_handoff','gpio_handoff_contract')):
            report[name]=getattr(p.package_source,factory)()
        return data,report

    def test_exact_scope_restoration_and_raw_only(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['gpio_observer_trial_pass']);self.assertTrue(result['gpio_mappings_revoked'])
        self.assertEqual(result['observed_field_rows'],53);self.assertEqual(result['endpoint_register_reads_completed'],60)
        self.assertEqual(result['gpio_snapshots'][0]['ctrl'],5)
        for key in ('gpio_register_writes','phy_reset_performed','gpio_electrical_state_proven','phy_ready_proven','ethernet_proven'):
            self.assertFalse(result[key])
        # The observer reports, not qualifies, all raw values; inconsistent
        # snapshots and all-ones never acquire a reset/electrical interpretation.
        raw=data.replace(b'GPIO1_CTRL STATUS=00032200 CTRL=00000005 PAD=00000056',
            b'GPIO1_CTRL STATUS=ffffffff CTRL=ffffffff PAD=ffffffff')
        got=p.inspect(raw,report);self.assertTrue(got['gpio_observer_trial_pass'])
        self.assertEqual(got['gpio_snapshots'][1]['ctrl'],0xffffffff);self.assertFalse(got['phy_ready_proven'])
        for before,after in ((b'GPIO STATE=2',b'GPIO STATE=3'),(b'READS=12 MAPPED=7',b'READS=11 MAPPED=7'),
            (b'MAPPED=7 UNMAPPED=7',b'MAPPED=7 UNMAPPED=3'),(b'INDEX=0\n',b'INDEX=3\n'),
            (b'PASS=1 WORD=5 PENDING=0',b'PASS=1 WORD=5 PENDING=1'),
            (b'PASS=1 WORD=5 PENDING=0',b'PASS=2 WORD=5 PENDING=0'),
            (p.package_source.DEVICE_MARKER.encode(),p.prior.package_source.DEVICE_MARKER.encode())):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        for field,value in (('reset_pin',32.0),('reset_active_low',1),('passes',True)):
            changed=copy.deepcopy(report);changed['gpio_contract'][field]=value
            with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_actual_full_recorder_api_and_entire_raw_fault_tail(self):
        method=full.RootForwardSerialTests.test_actual_original_complete_capture_api
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)
        data,report=self.fixture()
        for value in (b'panic(cpu 0 caller 0x1): failure\n',b'RPI5XNU:FAULT\n'):
            for offset in (0,data.index(p.PREFIX+b'END '),len(data)):
                with self.assertRaises(ValueError):p.inspect(data[:offset]+value+data[offset:],report)

    def test_partial_failure_preserves_live_unknown_not_restored(self):
        data,report=self.fixture()
        data=data.replace(b'GPIO STATE=2 RC=0 READS=12 MAPPED=7 UNMAPPED=7 INDEX=0',
            b'GPIO STATE=3 RC=-4 READS=3 MAPPED=7 UNMAPPED=0 INDEX=1')
        observed=[]
        def inspect(raw,metadata):
            result=p.inspect(raw,metadata);observed.append(result);return result
        proxy=types.SimpleNamespace(**vars(p));proxy.inspect=inspect
        method=full.RootForwardSerialTests.test_partial_failure_leaves_forwarding_unknown_not_restored
        old=b'COMMITTED=00070106 HZ=200000000';new=b'COMMITTED=00070109 HZ=200000000'
        self.assertEqual(method.__code__.co_consts.count(old),1)
        code=method.__code__.replace(co_consts=tuple(new if v==old else v for v in method.__code__.co_consts))
        with patch.object(self,'fixture',lambda:(data,report)):
            types.FunctionType(code,dict(method.__globals__,p=proxy))(self)
        result=observed[0];self.assertFalse(result['gpio_observer_trial_pass'])
        self.assertFalse(result['gpio_mappings_revoked']);self.assertFalse(result['gpio_snapshots_committed'])
        self.assertIsNone(result['endpoint_register_reads_completed'])


if __name__=='__main__':unittest.main()
