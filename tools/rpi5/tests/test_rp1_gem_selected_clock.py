# SPDX-License-Identifier: BSD-2-Clause
"""Actual decoder/state machine and full guarded path; no hardware clock model proof."""
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from tools.rpi5 import rp1_gem_selected_clock_profile as profile
from tools.rpi5.tests import test_pcie_root_forward_transport as prior


def source(folder,main,mutation=None):
    text=prior.source(folder,main)
    core=folder/'rp1_gem_identify.c';core.write_text(profile.gem_core(core.read_text()))
    return mutation(text) if mutation else text


def run(main,mutation=None):
    function=types.FunctionType(prior.run.__code__,dict(prior.run.__globals__,source=source),argdefs=prior.run.__defaults__)
    return function(main,mutation)


class GEMSelectedClockTests(unittest.TestCase):
    def test_actual_core_controls_selectors_pll_and_all_prior_faults(self):
        with tempfile.TemporaryDirectory(prefix='gem-selected-core-') as directory:
            folder=Path(directory);core=folder/'gem.c'
            core.write_text(profile.gem_core((profile.FROZEN/'rp1_gem_identify.c').read_text()))
            host=(Path(__file__).with_name('rp1_gem_identify_host.c')).read_text()
            # Old fixture lists CTRL2 as invalid; CTRL0 remains invalid instead.
            host=profile.util.once(host,'const uint32_t bad[]={2,0x803,','const uint32_t bad[]={0,0x803,')
            host=profile.util.once(host,'    unsigned faults=0;',r'''
    const uint32_t physical_before[15]={2,1,4,0x80000001,4,20,0,0x51010,
        0x10000800,1,1,0x10000800,1,1,0x80000800};
    reset();memcpy(clock_values,physical_before,sizeof physical_before);
    assert(rpi5_gem_clock_profile(clock_values));
    struct rpi5_gem_observation actual;
    assert(!rpi5_gem_identify_run(&session,&decode,&io,&actual)&&reads==32);
    for(unsigned bit=0;bit<32;bit++){
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_values[0]^=1u<<bit;
        if(bit==11){assert(rpi5_gem_clock_profile(clock_values));}
        else{assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);}
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_values[2]^=1u<<bit;assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_values[3]^=1u<<bit;assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_values[4]^=1u<<bit;
        if(bit!=1 && bit!=4){assert(!rpi5_gem_clock_profile(clock_values));rejected();assert(reads==15);}
    }
    /* Both allowed SYS controls still require exactly live SEL4. */
    for(unsigned enable=0;enable<2;enable++)for(unsigned sel=0;sel<32;sel++){
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_values[0]=enable?0x802:2;clock_values[2]=sel;
        assert(rpi5_gem_clock_profile(clock_values)==(sel==4));
    }
    for(unsigned n=1;n<=15;n++){
        reset();memcpy(clock_values,physical_before,sizeof physical_before);
        clock_change=n;rejected();assert(reads==32);
    }
    unsigned faults=0;''')
            test=folder/'host.c';test.write_text(host);exe=folder/'host'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(profile.ROOT/'loader/rpi5'),str(test),str(core),
                '-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')

    def test_single_predicate_delta_and_a76(self):
        with tempfile.TemporaryDirectory(prefix='gem-selected-target-') as directory:
            folder=Path(directory)/'overlay';sources=profile.emit(folder)
            self.assertEqual([s.name for s in sources],['rp1_gem_identify.c'])
            for old in profile.FROZEN.iterdir():
                if old.is_file() and old.name!='rp1_gem_identify.c':self.assertEqual(old.read_bytes(),(folder/old.name).read_bytes())
            old=(profile.FROZEN/'rp1_gem_identify.c').read_text();new=sources[0].read_text()
            strip=lambda s:re.sub(r'\s+','',re.sub(r'/\*.*?\*/','',s,flags=re.S))
            self.assertEqual(strip(new),strip(old.replace('!(v[0]&(1u<<11)) || (v[0]&3)!=2','(v[0]!=2 && v[0]!=0x802)')))
            command=['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
                '-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector','-O2',
                '-Wall','-Wextra','-Werror','-c',str(sources[0]),'-I',str(profile.ROOT/'loader/rpi5'),
                '-o',str(folder/'gem.o')]
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_full_original_transport_faults_parity_and_budget(self):
        for name in ('test_real_owner_failures_before_and_after_root_accesses',
            'test_all_prior_transport_operations_and_gem_reads_retained',
            'test_full_actual_owner_cost_complete_root_endpoint_restore',
            'test_old_path_cannot_bypass_explicit_root_forwarding_model'):
            function=getattr(prior.RootForwardTransportTests,name)
            types.FunctionType(function.__code__,dict(function.__globals__,run=run))(self)

    def test_actual_observed_words_full_path_cost_and_unchanged_operations(self):
        def physical_words(text):
            text=profile.util.once(text,
                'const uint32_t value[]={0x802,1,4,0x80000001,4,20,0,0x51000,0x800,1,2,0x800,1,2,0x80000800};',
                'const uint32_t value[]={2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800};')
            return prior.physical_route_model(text)
        def observed_run(main,mutation=None):
            return run(main,lambda text:physical_words(mutation(text) if mutation else text))
        function=prior.RootForwardTransportTests.test_full_actual_owner_cost_complete_root_endpoint_restore
        types.FunctionType(function.__code__,dict(function.__globals__,run=observed_run,physical_route_model=lambda text:text))(self)


if __name__=='__main__':unittest.main()
