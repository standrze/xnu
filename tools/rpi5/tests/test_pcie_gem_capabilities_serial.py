# SPDX-License-Identifier: BSD-2-Clause
import copy
import ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_gem_capabilities_serial_core as p
from tools.rpi5 import pcie_gem_capabilities_trace_profile as profile
from tools.rpi5.tests import test_pcie_gem_selected_serial as selected
from tools.rpi5.tests import test_pcie_root_forward_serial as full


class GEMCapabilitiesSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=selected.GEMSelectedSerialTests().fixture()
        data=data.replace(b'PCIE_GEM_SELECTED_TRIAL',b'PCIE_GEM_CAPABILITIES_TRIAL')
        raw=[0x70106,0x02000000,0x00b00000,0x100,0x08800003,0x02030405,0x1200,0x4000000]
        rows=[b'RPI5XNU:PCIEID:CAPS STATE=2 RC=0 READS=16 PASS=1 INDEX=7 PENDING=0']
        for side in ('BEFORE','AFTER'):
            for half,labels in enumerate(('MID DCFG1 DCFG2 DCFG5','DCFG6 DCFG8 DCFG10 DCFG12')):
                rows.append(p.PREFIX+('CAP_'+side+str(half)+' ').encode()+b' '.join(
                    ('%s=%08x'%(name,value)).encode() for name,value in zip(labels.split(),raw[half*4:half*4+4])))
        data=data.replace(p.PREFIX+b'END ',b'\n'.join(rows)+b'\n'+p.PREFIX+b'END ')
        report['marker']=report['marker'].replace('PCIE_GEM_SELECTED_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL')
        report['boot_markers']=[s.replace('PCIE_GEM_SELECTED_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL') for s in report['boot_markers']]
        for name,factory in (('capabilities_contract','capabilities_contract'),('root_forward_contract','root_forward_contract'),
            ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
            report[name]=getattr(p.package_source,factory)()
        return data,report

    def test_exact_read_scope_and_each_snapshot_or_count_mutation(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['capabilities_trial_pass']);self.assertEqual(result['observed_field_rows'],47)
        self.assertEqual(result['endpoint_register_reads_completed'],48)
        self.assertEqual(result['capabilities']['bus_width_bits'],32)
        self.assertEqual(result['capabilities']['queue_count'],2)
        self.assertFalse(result['ethernet_proven']);self.assertFalse(result['dma_addressability_qualified'])
        for before,after in ((b'READS=16 PASS=1',b'READS=15 PASS=1'),(b'CAPS STATE=2',b'CAPS STATE=3'),
            (b'PASS=1 INDEX=7',b'PASS=2 INDEX=7'),(b'INDEX=7 PENDING=0',b'INDEX=7 PENDING=1'),
            (b'CAP_AFTER0 MID=00070106',b'CAP_AFTER0 MID=00070109'),
            (b'CAP_AFTER1 DCFG6=08800003',b'CAP_AFTER1 DCFG6=08800002')):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        changed=copy.deepcopy(report);changed['capabilities_contract']['unchanged_pm_limit']=99999
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_complete_api_and_faults_before_after_end_and_return(self):
        method=full.RootForwardSerialTests.test_actual_original_complete_capture_api
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)
        data,report=self.fixture()
        for value in (b'panic(cpu 0 caller 0x1): failure\n',b'RPI5XNU:FAULT\n'):
            for offset in (0,data.index(p.PREFIX+b'END '),len(data)):
                with self.assertRaises(ValueError):p.inspect(data[:offset]+value+data[offset:],report)

    def test_valid_partial_failure_not_upgraded_to_success(self):
        data,report=self.fixture()
        data=data.replace(b'CAPS STATE=2 RC=0 READS=16 PASS=1 INDEX=7 PENDING=0',
            b'CAPS STATE=3 RC=-4 READS=9 PASS=1 INDEX=0 PENDING=0')
        observed=[]
        def inspect(raw,metadata):
            result=p.inspect(raw,metadata);observed.append(result);return result
        proxy=types.SimpleNamespace(**vars(p));proxy.inspect=inspect
        method=full.RootForwardSerialTests.test_partial_failure_leaves_forwarding_unknown_not_restored
        with patch.object(self,'fixture',lambda:(data,report)):
            types.FunctionType(method.__code__,dict(method.__globals__,p=proxy))(self)
        result=observed[0]
        self.assertFalse(result['capabilities_trial_pass']);self.assertFalse(result['capabilities_committed'])
        self.assertIsNone(result['capabilities']);self.assertIsNone(result['endpoint_register_reads_completed'])

    def test_decoder_matches_actual_c_all_single_bits_and_unknown_bus_width(self):
        with tempfile.TemporaryDirectory(prefix='gem-cap-parity-') as directory:
            folder=Path(directory);sources=profile.emit(folder/'overlay');lib=folder/'cap.dylib'
            result=subprocess.run(['xcrun','clang','-std=c11','-dynamiclib','-Wall','-Wextra','-Werror',
                '-I',str(folder/'overlay'),'-I',str(profile.ROOT/'loader/rpi5'),
                str(sources[1]),str(sources[2]),'-o',str(lib)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            base=[0x70106,0x02000000,0x00b00000,0x100,0x08800003,0x02030405,0x1200,0x4000000]
            keys=list(p.decode(base))
            class Observation(ctypes.Structure):
                _fields_=[('raw',ctypes.c_uint32*8),('reads',ctypes.c_uint32)]+[(key,ctypes.c_uint32) for key in keys]
            decode=ctypes.CDLL(str(lib)).rpi5_gem_cap_decode
            decode.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(Observation)];decode.restype=ctypes.c_int
            values=[base]
            for i in range(8):
                for bit in range(32):
                    value=list(base);value[i]^=1<<bit;values.append(value)
            for value in values:
                observed=Observation();rc=decode((ctypes.c_uint32*8)(*value),ctypes.byref(observed))
                try:python=p.decode(value)
                except ValueError:self.assertNotEqual(rc,0)
                else:
                    self.assertEqual(rc,0)
                    self.assertEqual(python,{k:getattr(observed,k) for k in keys})
            base[1]=0xe000000;self.assertEqual(p.decode(base)['bus_width_bits'],0)


if __name__=='__main__':unittest.main()
