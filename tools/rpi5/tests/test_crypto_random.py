# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hashlib
import hmac
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RandomTests(unittest.TestCase):
    def test_kmem_dispatch_and_no_reentry(self):
        # Independent HMAC-SHA256 DRBG first-output oracle for seed #2.
        key, value = bytes(32), bytes([1]) * 32
        seed = bytes(range(2, 34))
        for separator in (b'\x00', b'\x01'):
            key = hmac.new(key, value + separator + seed, hashlib.sha256).digest()
            value = hmac.new(key, value, hashlib.sha256).digest()
        first_output = hmac.new(key, value, hashlib.sha256).digest()
        source = r'''
#include "rpi5_crypto_random.h"
#include <libkern/crypto/register_crypto.h>
#include <bearssl_rand.h>
#include <assert.h>
#include <string.h>
#include <setjmp.h>
static jmp_buf trap_return;
static unsigned expect_trap;
static void test_trap(void) __attribute__((noreturn));
static void test_trap(void) { assert(expect_trap); longjmp(trap_return,1); }
#define __builtin_trap test_trap
#include "rpi5_crypto_random.c"
#undef __builtin_trap
#define TRAPS(call) do { expect_trap=1; if(!setjmp(trap_return)) { \
    call; assert(!"expected trap"); } expect_trap=0; } while(0)
static unsigned calls;
void read_random(void *p, unsigned int n) {
    assert(n==32); ++calls;
    for(unsigned i=0;i<n;i++) ((unsigned char *)p)[i]=(unsigned char)(i+calls);
}
static const struct crypto_functions f={
 .random_generate_fn=rpi5_crypto_random_generate,
 .random_uniform_fn=rpi5_crypto_random_uniform,
 .random_kmem_ctx_size_fn=rpi5_crypto_random_kmem_ctx_size,
 .random_kmem_init_fn=rpi5_crypto_random_kmem_init};
int main(void) {
    _Alignas(void *) unsigned char a[256],b[256];
    unsigned char seed[32],out[1027],expected[1025];
    assert(f.random_kmem_ctx_size_fn()<=sizeof a);
    memset(a,0xa5,sizeof a); memset(b,0xa5,sizeof b);
    f.random_kmem_init_fn(a); f.random_kmem_init_fn(b);
    assert(calls==2);
    unsigned char saved[256],saved_out[sizeof out];
    memset(out,0xa5,sizeof out); memcpy(saved,a,sizeof a);
    memcpy(saved_out,out,sizeof out);
    TRAPS(f.random_kmem_init_fn(NULL));
    TRAPS(f.random_kmem_init_fn(a+1));
    TRAPS(f.random_generate_fn(NULL,out,1));
    TRAPS(f.random_generate_fn(a+1,out,1));
    TRAPS(f.random_generate_fn(a,NULL,1));
    TRAPS(f.random_generate_fn(a,out,SIZE_MAX));
    TRAPS(f.random_generate_fn(a,a,1));
    TRAPS(f.random_generate_fn(a,a+sizeof(struct kmem_rng)-1,1));
    uint64_t uniform_out=123;
    _Alignas(uint64_t) unsigned char misaligned[16];
    memset(misaligned,0xa5,sizeof misaligned);
    TRAPS(f.random_uniform_fn(a,0,&uniform_out));
    TRAPS(f.random_uniform_fn(a,3,NULL));
    TRAPS(f.random_uniform_fn(a,3,(uint64_t *)(void *)(a+1)));
    TRAPS(f.random_uniform_fn(a,3,(uint64_t *)(void *)a));
    TRAPS(f.random_uniform_fn(a,3,(uint64_t *)(void *)(misaligned+1)));
    for(unsigned i=0;i<sizeof misaligned;i++) assert(misaligned[i]==0xa5);
    assert(uniform_out==123);
    assert(!memcmp(a,saved,sizeof a) && !memcmp(out,saved_out,sizeof out));
    struct kmem_rng *bad=(void *)a;
    bad->magic=0;
    TRAPS(f.random_generate_fn(a,out,1));
    memcpy(a,saved,sizeof a); bad->drbg.vtable=NULL;
    TRAPS(f.random_generate_fn(a,out,1));
    memcpy(a,saved,sizeof a); bad->drbg.digest_class=NULL;
    TRAPS(f.random_generate_fn(a,out,1));
    memcpy(a,saved,sizeof a);
    assert(!memcmp(out,saved_out,sizeof out) && calls==2);
    f.random_generate_fn(a,NULL,0);
    assert(!memcmp(a,saved,sizeof a));
    br_hmac_drbg_context reference;
    for(unsigned i=0;i<32;i++) seed[i]=(unsigned char)(i+1);
    br_hmac_drbg_init(&reference,&br_sha256_vtable,seed,32);
    for(size_t n=0;n<=1025;n++) {
        memset(out,0xa5,sizeof out);
        f.random_generate_fn(a,out+1,n);
        if(n) br_hmac_drbg_generate(&reference,expected,n);
        assert(!memcmp(out+1,expected,n));
        assert(out[0]==0xa5 && out[n+1]==0xa5);
    }
    const uint64_t bounds[]={1,2,3,17,UINT64_C(0x8000000000000001),UINT64_MAX};
    unsigned rejected=0;
    for(unsigned j=0;j<6;j++) for(unsigned k=0;k<100;k++) {
        uint64_t x,y,bound=bounds[j],threshold=(UINT64_C(0)-bound)%bound;
        do {
            br_hmac_drbg_generate(&reference,&x,sizeof x);
            if(x<threshold) ++rejected;
        } while(x<threshold);
        f.random_uniform_fn(a,bound,&y);
        assert(y==x%bound && y<bound);
    }
    assert(rejected>0);
    f.random_generate_fn(b,out,32);
    const unsigned char first_output[32]={FIRST_OUTPUT};
    assert(!memcmp(out,first_output,32));
    assert(memcmp(out,expected,32));
    assert(calls==2);
    for(size_t i=f.random_kmem_ctx_size_fn();i<256;i++) assert(a[i]==0xa5 && b[i]==0xa5);
}
'''.replace('FIRST_OUTPUT', ','.join(map(str, first_output)))
        lib = ROOT / 'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'libkern'),
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_ccrng.c'),
                *[str(lib/'src'/u) for u in ('rand/hmac_drbg.c','mac/hmac.c',
                    'hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
