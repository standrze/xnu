# SPDX-License-Identifier: BSD-2-Clause
"""Offline API/provider evidence, not entropy qualification or Pi execution."""
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_kernel_entropy_rand_probe as b
from tools.rpi5 import audit_apple_arc4random_closure as apple
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/kernel-entropy-rand-hfrb7y67'
MANIFEST_SHA='f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8'
APPLE_AUDIT=b.ROOT/'build/rpi5/apple-arc4random-normal-audit-7quo4726'
APPLE_SHA='a40bd8518eb230260c0413eaf91a79703a381d8c8575d198362f69984258c124'


class KernelEntropyRandTests(unittest.TestCase):
    def test_actual_target_dependencies_providers_and_failstop(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),MANIFEST_SHA)
        m=json.loads((PACKAGE/'manifest.json').read_text());validate_closure(PACKAGE,m)
        self.assertEqual(m['actual_constructor_order'],['_initialized_constructor'])
        self.assertTrue(m['target_link_complete']);self.assertEqual(m['target_missing_symbols'],[])
        for key in ('entropy_qualified','firmware_attestation','live_keys','raw_random_or_seed_output',
                    'installed','pi_executed','accepted_runtime_modified','apple_corecrypto_implementation',
                    'rc4_fallback','mutable_adapter_state','cached_generator','adapter_heap','adapter_lock'):
            self.assertIs(m[key],False)
        for key in ('adapter_is_project_code','native_syscall_is_double','any_syscall_error_is_fatal'):
            self.assertIs(m[key],True)
        base=json.loads((b.BASE/'manifest.json').read_text())
        old=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/rng-force-link.stdout')))
        replacement=m['exact_link_replacement'];old[old.index(replacement['old'])]=replacement['new']
        old[old.index('-o')+1]=str(PACKAGE/'target.unstripped');old[old.index('-map')+1]=str(PACKAGE/'target.map')
        old.append(m['added_adapter_object'])
        new=next(c['command'] for c in m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(old,new)
        self.assertEqual((PACKAGE/'adapter-imports.stdout').read_text().splitlines(),['__exit','_getentropy'])
        symbols=(PACKAGE/'adapter-symbols.stdout').read_text()
        self.assertNotIn('__DATA',symbols);self.assertNotIn('__thread',symbols)
        dis=(PACKAGE/'target-contract.stdout').read_text()
        functions=dict(re.findall(r'<([^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',dis,re.S))
        self.assertRegex(functions['_getentropy'],r'mov\s+x16, #0x1f4')
        self.assertRegex(functions['__exit'],r'mov\s+x16, #0x1\s')
        self.assertIn('<_arc4random_buf>',functions['_RAND_bytes'])
        self.assertIn('<_getentropy>',functions['_arc4random_buf'])
        self.assertRegex(functions['_arc4random_buf'],r'cbz\s+x1,')
        self.assertRegex(functions['_arc4random_buf'],r'cbz\s+x0,')
        self.assertIn('#0x100',functions['_arc4random_buf'])
        fatal=functions['_random_request_failed']
        self.assertIn('#0x7f',fatal);self.assertRegex(fatal,r'blr\s+x8')
        self.assertRegex(fatal,r'brk\s+#0x1');self.assertNotRegex(fatal,r'\bret\b')
        body=functions['_rpi5_pthread_smoke_main']
        self.assertLess(body.index('<_rpi5_packet_pthread_prerequisite>'),body.index('<_RAND_bytes>'))
        self.assertIn('strb\twzr',body)  # volatile wipe after every original RAND call
        linkmap=(PACKAGE/'target.map').read_text()
        self.assertRegex(linkmap,r'\[\s*1\]\s+_getentropy\n')
        self.assertRegex(linkmap,r'\[\s*1\]\s+__exit\n')
        self.assertIn('rand_lib.c.o',linkmap);self.assertIn('kernel-entropy-adapter.o',linkmap)
        for field in ('headers_sha256','generated_sha256'):
            altered=copy.deepcopy(m);altered[field].pop(next(iter(altered[field])))
            with self.assertRaises(ValueError):validate_closure(PACKAGE,altered)

    def test_real_adapter_and_original_rand_with_explicit_syscall_doubles(self):
        m=json.loads((PACKAGE/'manifest.json').read_text())
        result=subprocess.run([PACKAGE/'host-contract'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,m['native_stdout'])
        self.assertIn('BOUNDARIES=11 FATAL=8 THREADS=4 FORK_WHILE_ACTIVE=1',result.stdout)
        self.assertIn('ORIGINAL_RAND_BYTES=1 SYSCALL_DOUBLES_NOT_ENTROPY',result.stdout)
        compile_row=next(c for c in m['commands'] if c['stdout'].endswith('/host-original-rand-compile.stdout'))
        self.assertIn(m['original_rand_source'],compile_row['command'])
        self.assertIn('-Darc4random_buf=fixture_arc4random_buf',compile_row['command'])
        self.assertIn('-fsanitize=address,undefined',compile_row['command'])

    def test_original_apple_full_tu_failure_is_preserved_not_false_closure(self):
        self.assertEqual(b.sha(APPLE_AUDIT/'manifest.json'),APPLE_SHA)
        m=json.loads((APPLE_AUDIT/'manifest.json').read_text());validate_closure(APPLE_AUDIT,m)
        self.assertEqual(m['actual_consumed_headers_sha256'],m['headers_sha256'])
        self.assertFalse(m['compile_complete']);self.assertFalse(m['link_attempted'])
        self.assertFalse(m['original_source_modified']);self.assertFalse(m['variant_static_selected'])
        self.assertFalse(m['rc4_fallback_selected']);self.assertTrue(m['gap_lists_valid_only_when_link_attempted'])
        self.assertTrue(any('os_log_send_and_compose' in line for line in m['compile_diagnostics']))
        self.assertTrue(any('OS_LOG_F_SEND' in line for line in m['compile_diagnostics']))
        self.assertEqual((APPLE_AUDIT/'original-source.stdout').read_text(),apple.SOURCE.read_text())
        license_text=(b.ROOT/'EXTERNAL_HEADERS/corecrypto/ccrng.h').read_text()
        self.assertIn('Internal Use License Agreement',license_text)
        self.assertIn('redistribute the Apple Software',license_text)
        feature=next(c for c in m['commands'] if c['stdout'].endswith('/generate-original-features.stdout'))
        self.assertEqual(feature['environment_overrides']['ARCHS'],'arm64')
        self.assertEqual(feature['environment_overrides']['VARIANT_PLATFORM_NAME'],'macosx')

    def test_original_apple_wrapper_requires_a_nonreturning_failure_provider(self):
        original=apple.SOURCE.read_text()
        # Exact normal function bodies; the enclosing platform/private headers
        # are replaced only in this explicit native contract harness.
        body=original.split('static struct ccrng_state *rng;',1)[1].split('#else /* __APPLE__ && !VARIANT_STATIC */',1)[0]
        body='static struct ccrng_state *rng;'+body
        prefix=r'''
#include <assert.h>
#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
#define __private_extern__
#define OS_CRASH_ENABLE_EXPERIMENTAL_LIBTRACE 1
typedef unsigned char u_char;
struct ccrng_state { int (*generate)(struct ccrng_state *, size_t, void *); };
static unsigned generates, uniforms, crash_count;
static int fail_generation, null_handle;
static jmp_buf crash;
static int fixture_generate(struct ccrng_state *r,size_t n,void *out) {
 (void)r; generates++; if(fail_generation) return 5; memset(out,0xa5,n); return 0;
}
static struct ccrng_state state={fixture_generate};
static struct ccrng_state *ccrng(int *error){*error=null_handle?5:0;return null_handle?NULL:&state;}
#define ccrng_generate(r,n,p) ((r)->generate((r),(n),(p)))
static int ccrng_uniform(struct ccrng_state *r,uint64_t bound,uint64_t *v){
 (void)r;(void)bound;uniforms++;*v=7;return 5;
}
#define os_crash(...) do {crash_count++;longjmp(crash,1);}while(0)
#define arc4random_addrandom fixture_apple_addrandom
#define arc4random fixture_apple_random
#define arc4random_buf fixture_apple_buf
#define arc4random_stir fixture_apple_stir
#define arc4random_uniform fixture_apple_uniform
#define _arc4_fork_child fixture_apple_fork_child
void fixture_apple_buf(void *,size_t);
'''
        suffix=r'''
int main(void){
 unsigned char b[4]={0};fixture_apple_buf(b,sizeof(b));assert(generates==1&&b[0]==0xa5);
 fail_generation=1;memset(b,0x5a,sizeof(b));fixture_apple_buf(b,sizeof(b));
 assert(generates==2&&b[0]==0x5a); /* void wrapper ignores provider status */
 assert(fixture_apple_uniform(16)==7&&uniforms==1); /* error also ignored */
 rng=NULL;null_handle=1;
 if(!setjmp(crash)){fixture_apple_buf(b,sizeof(b));assert(0);}
 assert(crash_count==1);
 puts("ORIGINAL_APPLE_NORMAL_WRAPPER_CONTRACT_PASS PROVIDER_FAILURE_MUST_NOT_RETURN NOT_REAL_RNG");
}
'''
        with tempfile.TemporaryDirectory() as name:
            source=Path(name)/'contract.c';exe=Path(name)/'contract'
            source.write_text(prefix+body+suffix)
            run=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                source,'-o',exe],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('NOT_REAL_RNG',result.stdout)


if __name__=='__main__':unittest.main()
