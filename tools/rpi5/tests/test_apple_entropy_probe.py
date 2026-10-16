# SPDX-License-Identifier: BSD-2-Clause
"""Narrow source/ABI/link evidence, never entropy quality or target execution."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_apple_entropy_probe as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=Path(os.environ.get('RPI5_ENTROPY_PACKAGE',str(b.ROOT/'build/rpi5/apple-entropy-api-x4zxvaug'))).resolve()


class EntropyProbeTests(unittest.TestCase):
    def test_actual_target_closure_syscall_and_missing_real_rng_provider(self):
        m=json.loads((PACKAGE/'manifest.json').read_text());validate_closure(PACKAGE,m)
        self.assertEqual(m['actual_constructor_order'],['_initialized_constructor'])
        self.assertEqual(m['forced_rand_bytes_missing'],['_arc4random_buf'])
        dis=(PACKAGE/'target-contract.stdout').read_text()
        self.assertIn('<_getentropy>:',dis);self.assertRegex(dis,r'mov\s+x16, #0x1f4')
        self.assertIn('<_sysctlbyname>:',dis)
        for key in ('entropy_qualified','live_keys','installed','pi_executed','raw_random_or_seed_output',
                    'random_output_hashing','health_counters_are_quality_proof','firmware_attestation'):
            self.assertIs(m[key],False)
        base=json.loads((b.BASE/'manifest.json').read_text())
        old=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        replace=m['exact_link_replacement'];old=[replace['new'] if p==replace['old'] else p for p in old]
        old=[p for p in old if p not in m['removed_unused_packet_inputs']]
        old[old.index('-o')+1]=str(PACKAGE/'target.unstripped');old[old.index('-map')+1]=str(PACKAGE/'target.map')
        new=next(c['command'] for c in m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(new,old)
        for field in ('headers_sha256','generated_sha256'):
            altered=copy.deepcopy(m);altered[field].pop(next(iter(altered[field])))
            with self.assertRaises(ValueError):validate_closure(PACKAGE,altered)

    def test_actual_diagnostic_with_explicit_api_failure_doubles(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name);obj=out/'probe.o';exe=out/'host'
            flags=['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
            subprocess.run(flags+['-Dgetentropy=fixture_getentropy','-Dsysctlbyname=fixture_sysctlbyname',
                '-c',str(b.SOURCE),'-o',str(obj)],check=True,capture_output=True,text=True)
            subprocess.run(flags+[str(b.ROOT/'tools/rpi5/tests/entropy_api_contract.c'),str(obj),'-o',str(exe)],
                check=True,capture_output=True,text=True)
            for mode,status in enumerate((0,0,20,20,20,21,11,12,13,7)):
                result=subprocess.run([exe,str(mode)],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,status,(mode,result.stderr));self.assertEqual(result.stderr,'')
                self.assertNotIn('a5a5',result.stdout)
                if mode < 6:
                    self.assertEqual(result.stdout.count('RPI5XNU:ENTROPY:COUNTER '),10)
                    self.assertIn('QUALITY_NOT_PROVEN',result.stdout)
                else:self.assertNotIn('API_OK',result.stdout)

    def test_original_xnu_getentropy_size_and_copyout_contract(self):
        source=(b.ROOT/'bsd/dev/random/randomdev.c').read_text()
        function=re.search(r'\nint\ngetentropy\([^\n]+\n\{.*?\n\}',source,re.S)[0]
        pre=r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
#define getentropy actual_kernel_getentropy
typedef uint64_t user_addr_t;
typedef uint64_t user_size_t;
typedef unsigned u_int;
struct proc { int unused; };
struct getentropy_args { uint64_t buffer, size; };
static unsigned reads,copies;
static void read_random(void *p,unsigned n){reads++;assert(n<=256);memset(p,0xa5,n);}
static int copyout(const void *p,uint64_t out,uint64_t n){
 copies++;assert(n<=256);if(out==1)return EFAULT;
 const unsigned char *v=p;for(unsigned i=0;i<n;i++)assert(v[i]==0xa5);
 return 0;
}
'''
        post=r'''
int main(void){
 struct getentropy_args a={0x1000,0};
 for(unsigned n=0;n<=256;n++){a.size=n;assert(!actual_kernel_getentropy(0,&a,0));}
 assert(reads==257&&copies==257);
 a.size=257;assert(actual_kernel_getentropy(0,&a,0)==EINVAL);
 a.size=UINT64_MAX;assert(actual_kernel_getentropy(0,&a,0)==EINVAL);
 assert(reads==257&&copies==257);
 a.size=1;a.buffer=1;assert(actual_kernel_getentropy(0,&a,0)==EFAULT);
 assert(reads==258&&copies==258);
 puts("XNU_GETENTROPY_CONTRACT_PASS LENGTHS=257 OVERSIZE=2 COPYOUT_FAULT=1 API_DOUBLES_NOT_ENTROPY");
}
'''
        with tempfile.TemporaryDirectory() as name:
            source=Path(name)/'contract.c';exe=Path(name)/'contract';source.write_text(pre+function+post)
            compiled=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                str(source),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('API_DOUBLES_NOT_ENTROPY',result.stdout)


if __name__=='__main__':unittest.main()
