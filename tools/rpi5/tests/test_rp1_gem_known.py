# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from tools.rpi5 import rp1_gem_known_clock_profile as profile
from tools.rpi5.tests import test_rp1_gem_transport as prior


def source(folder,main,mutation=None):
    text=prior.source(folder,main,mutation)
    path=folder/'rp1_gem_identify.c';path.write_text(profile.gem_core(path.read_text()))
    return text


run=types.FunctionType(prior.run.__code__,dict(prior.run.__globals__,source=source,profile=profile),argdefs=prior.run.__defaults__)


class GEMKnownClockTests(unittest.TestCase):
    def test_actual_core_unknown_cs_and_pwr_bits_and_prior_faults(self):
        with tempfile.TemporaryDirectory(prefix='gem-known-core-') as directory:
            folder=Path(directory);src=folder/'gem.c';src.write_text(profile.gem_core((profile.ROOT/'loader/rpi5/rp1_gem_identify.c').read_text()))
            host=(Path(__file__).with_name('rp1_gem_identify_host.c')).read_text()
            host=profile.util.once(host,'    unsigned faults=0;',r'''
    for(unsigned bit=0;bit<32;bit++){
        reset();clock_values[3]^=1u<<bit;
        if(!(UINT32_C(0x8000003f)&(1u<<bit))){assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);}
        reset();clock_values[4]^=1u<<bit;
        if(!(UINT32_C(0x3f)&(1u<<bit))){assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);}
    }
    unsigned faults=0;''')
            test=folder/'host.c';test.write_text(host);exe=folder/'host'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(profile.ROOT/'loader/rpi5'),str(test),str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')

    def test_all_actual_transport_faults_and_operation_parity(self):
        for name in ('test_full_actual_owner_cost_mapping_and_restore','test_bad_clock_and_mid_fail_without_unmap_or_compensation',
            'test_predecessor_operations_identical_plus_exact_read_only_addition','test_real_owner_failures_before_and_after_register_reads'):
            method=getattr(prior.GEMTransportTests,name)
            types.FunctionType(method.__code__,dict(method.__globals__,run=run))(self)


if __name__=='__main__':unittest.main()
