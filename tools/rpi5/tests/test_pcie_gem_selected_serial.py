# SPDX-License-Identifier: BSD-2-Clause
import copy
import ctypes
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from tools.rpi5 import pcie_gem_selected_serial_core as p
from tools.rpi5 import rp1_gem_selected_clock_profile as profile
from tools.rpi5.tests import test_pcie_root_forward_serial as old


class GEMSelectedSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.RootForwardSerialTests().fixture()
        data=data.replace(b'PCIE_ROOT_FORWARD_TRIAL',b'PCIE_GEM_SELECTED_TRIAL')
        for before,after in ((b'CTRL=00000802',b'CTRL=00000002'),(b'PRIM=00051000',b'PRIM=00051010'),
            (b'ETH_CTRL=00000800',b'ETH_CTRL=10000800'),(b'TSU_CTRL=00000800',b'TSU_CTRL=10000800'),
            (b'ETH_SEL=00000002',b'ETH_SEL=00000001'),(b'TSU_SEL=00000002',b'TSU_SEL=00000001')):
            data=data.replace(before,after)
        report['marker']=report['marker'].replace('PCIE_ROOT_FORWARD_TRIAL','PCIE_GEM_SELECTED_TRIAL')
        report['boot_markers']=[v.replace('PCIE_ROOT_FORWARD_TRIAL','PCIE_GEM_SELECTED_TRIAL') for v in report['boot_markers']]
        for name,factory in (('selected_clock_contract','selected_clock_contract'),('root_forward_contract','root_forward_contract'),
            ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
            report[name]=getattr(p.package_source,factory)()
        return data,report

    def test_exact_selected_profile_success_full_restore_and_negatives(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['selected_clock_trial_pass']);self.assertTrue(result['gem_identification_proven'])
        self.assertFalse(result['clock_readiness_independently_proven']);self.assertFalse(result['physical_frequency_or_gate_measurement'])
        self.assertEqual(result['clock_snapshots'][0],[2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800])
        for before,after in ((b'CTRL=00000002',b'CTRL=00000402'),(b'SEL=00000004',b'SEL=00000000'),
            (b'SEL=00000004',b'SEL=00000005'),(b'CS=80000001',b'CS=00000001'),
            (b'PWR=00000004',b'PWR=00000005'),(b'DIV=00000001 SEL=00000004',b'DIV=00000002 SEL=00000004')):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(b'CTRL=00000002',b'CTRL=00000802',1),report)
        changed=copy.deepcopy(report);changed['selected_clock_contract']['physical_frequency_or_gate_measurement']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_all_prior_root_restore_failure_health_and_original_capture_api(self):
        for name in ('test_exact_success_preserves_status_and_original_nonidentical_window',
            'test_full_original_health_order_and_contract','test_actual_original_complete_capture_api',
            'test_partial_failure_leaves_forwarding_unknown_not_restored'):
            function=getattr(old.RootForwardSerialTests,name)
            types.FunctionType(function.__code__,dict(function.__globals__,p=p))(self)

    def test_python_clock_decoder_matches_actual_c_on_all_singlebit_mutations(self):
        with tempfile.TemporaryDirectory(prefix='gem-selected-parity-') as directory:
            folder=Path(directory);src=folder/'gem.c';src.write_text(profile.gem_core((profile.FROZEN/'rp1_gem_identify.c').read_text()))
            lib=folder/'libgem.dylib'
            result=subprocess.run(['xcrun','clang','-std=c11','-dynamiclib','-Wall','-Wextra','-Werror',
                '-I',str(profile.ROOT/'loader/rpi5'),str(src),'-o',str(lib)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            function=ctypes.CDLL(str(lib)).rpi5_gem_clock_profile;function.argtypes=[ctypes.POINTER(ctypes.c_uint32)];function.restype=ctypes.c_int
            base=[2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800]
            cases=[base,list(base)];cases[1][0]=0x802
            for n in range(15):
                for bit in range(32):
                    value=list(base);value[n]^=1<<bit;cases.append(value)
            for value in cases:self.assertEqual(p.clock_profile(value),bool(function((ctypes.c_uint32*15)(*value))))


if __name__=='__main__':unittest.main()
