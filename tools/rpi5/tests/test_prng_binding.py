# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hmac
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class BindingTests(unittest.TestCase):
    def test_actual_callback_abi_and_personalization(self):
        seed=hmac.digest(bytes(range(64)),b'rpi5-xnu/kernel-prng/v1'+bytes(range(8)),'sha512')
        material=hmac.digest(seed,b'rpi5-xnu/generator/v1'+bytes(4),'sha256')
        k=bytes(32); v=bytes([1])*32
        for sep in (b'\0',b'\1'):
            k=hmac.digest(k,v+sep+material,'sha256'); v=hmac.digest(k,v,'sha256')
        expected=hmac.digest(k,v,'sha256')
        code=r'''
#include "rpi5_prng_binding.h"
#include <assert.h>
#include <string.h>
#include <setjmp.h>
static unsigned held,reads,expect_panic,health_failure;
static jmp_buf panic_return;
void rpi5_prng_binding_panic(const char *message) {
    assert(message && expect_panic && !held);
    longjmp(panic_return,1);
}
#define PANICS(call) do { expect_panic=1; if(!setjmp(panic_return)) { \
    call; assert(!"expected binding panic"); } expect_panic=0; } while(0)
static void lock(void *p) { (void)p; assert(!held); held=1; }
static void unlock(void *p) { (void)p; assert(held); held=0; }
static int try_lock(void *p) { (void)p; if(held)return 0; held=1; return 1; }
static int32_t entropy(size_t *n,void *p,void *arg) {
    (void)p; (void)arg; assert(held && *n==64); *n=0; reads++;
    return health_failure ? -1 : 0;
}
int main(void) {
    unsigned char seed[64],nonce[8],out[32];
    const unsigned char expected[32]={EXPECTED};
    for(unsigned i=0;i<64;i++)seed[i]=i;
    for(unsigned i=0;i<8;i++)nonce[i]=i;
    struct rpi5_prng_lock ops={lock,try_lock,unlock,0};
    const struct cckprng_funcs *f=&rpi5_prng_binding_functions;
    struct cckprng_ctx *ctx=rpi5_prng_binding_context();
    PANICS(f->generate(ctx,0,32,out));
    assert(rpi5_prng_binding_prepare(0)==-1);
    assert(!rpi5_prng_binding_prepare(&ops));
    assert(rpi5_prng_binding_prepare(&ops)==-1);
    assert(!f->init);
    PANICS(f->generate(0,0,32,out));
    PANICS(f->init_with_getentropy(ctx,0,64,seed,8,nonce,entropy,0));
    PANICS(f->init_with_getentropy(ctx,4,63,seed,8,nonce,entropy,0));
    PANICS(f->init_with_getentropy(ctx,4,64,seed,7,nonce,entropy,0));
    PANICS(f->init_with_getentropy(ctx,4,64,seed,8,nonce,0,0));
    f->init_with_getentropy(ctx,4,64,seed,8,nonce,entropy,0);
    PANICS(f->init_with_getentropy(ctx,4,64,seed,8,nonce,entropy,0));
    PANICS(f->generate(ctx,0,32,out));
    f->initgen(ctx,0);
    PANICS(f->initgen(ctx,0));
    PANICS(f->initgen(ctx,4));
    f->generate(ctx,0,32,out);
    assert(!memcmp(out,expected,32) && !held);
    f->reseed(ctx,64,seed);
    f->refresh(ctx); assert(reads==1 && !held);
    held=1; f->refresh(ctx); assert(reads==1 && held); held=0;
    f->initgen(ctx,1); f->generate(ctx,1,32,out);
    for(unsigned i=0;i<64;i++)assert(seed[i]==i);
    for(unsigned i=0;i<8;i++)assert(nonce[i]==i);
    health_failure=1;
    PANICS(f->refresh(ctx)); assert(reads==2);
    memset(out,0xa5,sizeof out);
    PANICS(f->generate(ctx,0,32,out));
    for(unsigned i=0;i<sizeof out;i++)assert(out[i]==0xa5);
    PANICS(f->reseed(ctx,64,seed));
    PANICS(f->initgen(ctx,2));
    PANICS(f->refresh(ctx)); assert(reads==2);
}
'''.replace('EXPECTED',','.join(map(str,expected)))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            deps=subprocess.run(['xcrun','clang','-M','-idirafter',str(ROOT/'EXTERNAL_HEADERS'),
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),str(p/'test.c')],
                check=True,capture_output=True,text=True).stdout
            self.assertIn(str(ROOT/'EXTERNAL_HEADERS/corecrypto/cckprng.h'),deps)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-idirafter',str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                *[str(ROOT/'osfmk/prng'/u) for u in ('rpi5_prng_binding.c','rpi5_prng_provider.c','rpi5_prng_refresh.c','rpi5_prng_generator.c')],
                *[str(lib/'src'/u) for u in ('rand/hmac_drbg.c','mac/hmac.c','hash/sha2small.c','hash/sha2big.c','codec/dec32be.c','codec/enc32be.c','codec/dec64be.c','codec/enc64be.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
