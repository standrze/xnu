# SPDX-License-Identifier: BSD-2-Clause
"""Actual candidate and original dispatch/wrapper; host doubles, never reboot."""
import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import psci_restart_candidate_profile as profile
from tools.rpi5.tests.test_pcie_fdt import _encode_fdt, _node

ROOT = profile.ROOT


def fixture():
    return _node('', {'compatible': b'raspberrypi,5-model-b\0brcm,bcm2712\0'},
        _node('psci', {'compatible': b'arm,psci-1.0\0arm,psci-0.2\0', 'method': b'smc\0'}))


def function(raw, start):
    at = raw.index(start); begin = raw.index('{', at); depth = 1; end = begin + 1
    while depth:
        depth += (raw[end] == '{') - (raw[end] == '}'); end += 1
    return raw[begin:end]


class PSCIRestartCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.work = Path(cls.temp.name)
        cls.program = cls.work/'native'
        cls.run_checked(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-I',ROOT/'loader/rpi5',
            ROOT/'tools/rpi5/tests/psci_restart_candidate_host.c',
            ROOT/'loader/rpi5/psci_restart_candidate.c', ROOT/'loader/rpi5/fdt.c',
            ROOT/'loader/rpi5/ranges.c','-o',cls.program])

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    @staticmethod
    def run_checked(command):
        r = subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=45)
        if r.returncode or r.stderr: raise AssertionError(str(command)+'\n'+r.stdout+r.stderr)
        return r.stdout

    def check(self, tree, accept=False):
        path = self.work/'tree.dtb'; path.write_bytes(tree if isinstance(tree,bytes) else _encode_fdt(tree))
        output = self.run_checked([self.program,path,'accept' if accept else 'reject'])
        self.assertIn('RESTART_POLICY PASS' if accept else 'RESTART_BINDING_REJECT NO_SMC=1',output)

    def test_actual_native_policy_errors_return_reentry_and_sixteen_callers(self):
        self.check(fixture(),True)

    def test_actual_parser_wrong_board_method_status_duplicates_and_truncation(self):
        tree = fixture(); raw = _encode_fdt(tree)
        for end in range(len(raw)): self.check(raw[:end] or b'0')
        for name,value in [('method',b'hvc\0'),('method',b'smc'),('method',b'smc\0junk'),
                           ('status',b'disabled\0'),('compatible',b'arm,psci\0')]:
            bad=copy.deepcopy(tree);bad['children'][0]['properties'][name]=value;self.check(bad)
        for name,value in [('compatible',b'raspberrypi,4-model-b\0brcm,bcm2711\0'),
                           ('compatible',b'raspberrypi,5-model-b\0brcm,bcm2712\0brcm,bcm2712\0'),
                           ('compatible',b'raspberrypi,5-model-b\0brcm,bcm2712'),
                           ('status',b'disabled\0')]:
            bad=copy.deepcopy(tree);bad['properties'][name]=value;self.check(bad)
        bad=copy.deepcopy(tree);bad['children'].append(copy.deepcopy(bad['children'][0]));self.check(bad)
        for name in ('compatible','method'):
            bad=copy.deepcopy(tree);del bad['children'][0]['properties'][name];self.check(bad)
        for method in (b'ok\0',b'okay\0'):
            good=copy.deepcopy(tree);good['properties']['status']=method;good['children'][0]['properties']['status']=method
            self.check(good,True)

    def test_actual_original_platform_dispatch_default_off_and_opt_in(self):
        original=profile.ORIGINAL.read_text(); derived=profile.derive(original)
        with self.assertRaises(ValueError):profile.derive(original+' ')
        method=function(derived,'IOPlatformExpert::haltRestart(unsigned int type)')
        header=(ROOT/'iokit/IOKit/IOPlatformExpert.h').read_text()
        enum_marker='enum {\n\tkPEHaltCPU,'
        self.assertEqual(header.count(enum_marker),1)
        enum=enum_marker+header.split(enum_marker,1)[1].split('};',1)[0]+'};'
        self.assertIn('kPEHaltCPU,\n\tkPERestartCPU,',enum)
        common='''#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
EXACT_PLATFORM_ENUM
static int option_present,option_value,view_ok=1,attempts,seen_type;
static bool PE_parse_boot_argn(const char *key,void *value,int size) {
    assert(!strcmp(key,"rpi5_psci_restart")&&size==4);*(int*)value=option_value;return option_present;
}
#define DEVELOPMENT 1
#define ARM64_BOARD_CONFIG_BCM2712 1
#define RPI5_FIRMWARE_FDT_HANDOFF 1
'''+profile.INCLUDE+'''
#include "loader/rpi5/psci_restart_candidate.h"
extern "C" bool rpi5_firmware_fdt_view(const void **tree,size_t *bytes) {
    if(!view_ok)return false;*tree=(void*)0x1000;*bytes=100;return true;
}
extern "C" int rpi5_restart_attempt(struct rpi5_restart_once *once,const void *tree,size_t bytes) {
    assert(once&&tree==(void*)0x1000&&bytes==100);attempts++;return RPI5_RESTART_RETURNED;
}
static int (*PE_halt_restart)(unsigned int);
static int platform(unsigned type) METHOD
static int original_callback(unsigned type){seen_type=(int)type;return 73;}
int main() {
    for(int present=0;present<2;present++)for(int value=-1;value<=2;value++)
    for(unsigned type=0;type<14;type++) {
        if(type==kPEHangCPU)continue;
        attempts=0;option_present=present;option_value=value;
        int result=platform(type);assert(result==(type==kPEPanicSync?0:-1));
        assert(attempts==(ENABLED&&present&&value==1&&type==kPERestartCPU));
    }
    option_present=option_value=1;view_ok=0;attempts=0;assert(platform(kPERestartCPU)==-1&&!attempts);
    view_ok=1;PE_halt_restart=original_callback;
    assert(platform(kPERestartCPU)==73&&seen_type==kPERestartCPU&&!attempts);
    assert(platform(kPEUPSDelayHaltCPU)==73&&seen_type==kPEHaltCPU&&!attempts);
    puts("ORIGINAL_PLATFORM_DISPATCH PASS NO_REAL_RESET");
}
'''.replace('METHOD',method)
        common=common.replace('EXACT_PLATFORM_ENUM',enum)
        for enabled in (0,1):
            source=self.work/('dispatch'+str(enabled)+'.cpp');source.write_text(common.replace('ENABLED',str(enabled)))
            exe=self.work/('dispatch'+str(enabled))
            self.run_checked(['xcrun','clang++','-std=c++17','-U__x86_64__','-fsanitize=address,undefined',
                '-DRPI5_PSCI_RESTART_CANDIDATE='+str(enabled),'-I',ROOT,source,'-o',exe])
            self.assertEqual(self.run_checked([exe]),'ORIGINAL_PLATFORM_DISPATCH PASS NO_REAL_RESET\n')

    def test_original_apple_reboot_wrapper_forwards_options_message_and_error(self):
        original=ROOT/'libsyscall/wrappers/reboot.c'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
            '5666536fb906adf4eb3a9b6067c9625c2d7f0e810e7e25f0b8837b50024b13c2')
        source=self.work/'wrapper.c';source.write_text('''#include <assert.h>
#include <errno.h>
#include <stdio.h>
int fixture_reboot(int);int fixture_reboot_np(int,const char*);
static int seen;static const char *message;
int fixture_trap(int flags,const char *p){seen=flags;message=p;errno=13;return -1;}
int main(void){const char *p="test";
assert(fixture_reboot(0x400)==-1&&seen==0x400&&!message&&errno==13);
assert(fixture_reboot_np(0x800,p)==-1&&seen==0x800&&message==p&&errno==13);
puts("ORIGINAL_APPLE_REBOOT_WRAPPER PASS TRAP_DOUBLE_ONLY");}
''')
        exe=self.work/'wrapper'
        self.run_checked(['xcrun','clang','-fsanitize=address,undefined','-Dreboot=fixture_reboot',
            '-Dreboot_np=fixture_reboot_np','-D__reboot=fixture_trap',original,source,'-o',exe])
        self.assertIn('ORIGINAL_APPLE_REBOOT_WRAPPER PASS',self.run_checked([exe]))


if __name__=='__main__':unittest.main()
