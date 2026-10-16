# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class ProviderTests(unittest.TestCase):
    def test_shared_lock_refresh_and_failure(self):
        code=r'''
#include "rpi5_prng_provider.h"
#include <assert.h>
#include <pthread.h>
#include <errno.h>
#include <string.h>
static struct rpi5_prng_provider provider;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static unsigned reads;
static int failure;
static void lock(void *p) { assert(!pthread_mutex_lock(p)); }
static void unlock(void *p) { assert(!pthread_mutex_unlock(p)); }
static int try_lock(void *p) { int r=pthread_mutex_trylock(p); assert(!r || r==EBUSY); return !r; }
static int32_t entropy(size_t *n,void *p,void *arg) {
    (void)arg; reads++; assert(*n==64);
    if(failure) { *n=0; return -1; }
    memset(p,0x42,64); *n=64; return 576;
}
static void *worker(void *arg) {
    (void)arg; unsigned char out[32];
    for(unsigned i=0;i<1000;i++) assert(!rpi5_provider_generate(&provider,0,out,sizeof out));
    return 0;
}
int main(void) {
    unsigned char seed[64],out[32]; memset(seed,0x5a,64);
    struct rpi5_prng_lock ops={lock,try_lock,unlock,&mutex};
    assert(rpi5_provider_init(&provider,65,seed,&ops,entropy,0)==-1);
    assert(!rpi5_provider_init(&provider,4,seed,&ops,entropy,0));
    assert(rpi5_provider_init(&provider,4,seed,&ops,entropy,0)==-1);
    assert(rpi5_provider_generate(&provider,0,out,32)==-1);
    assert(!rpi5_provider_initgen(&provider,0));
    assert(rpi5_provider_initgen(&provider,0)==-1);
    assert(rpi5_provider_initgen(&provider,4)==-1);
    pthread_t a,b;
    assert(!pthread_create(&a,0,worker,0)); assert(!pthread_create(&b,0,worker,0));
    assert(!pthread_join(a,0)); assert(!pthread_join(b,0));
    assert(provider.generators[0].requests==2000);
    lock(&mutex);
    assert(rpi5_provider_refresh(&provider)==RPI5_REFRESH_BUSY && !reads);
    unlock(&mutex);
    assert(!rpi5_provider_mix(&provider,seed,64));
    assert(provider.generators[0].requests==2000);
    assert(rpi5_provider_refresh(&provider)==RPI5_REFRESH_RESEEDED && reads==1);
    assert(!provider.generators[0].requests);
    assert(!rpi5_provider_initgen(&provider,1));
    assert(!rpi5_provider_generate(&provider,1,out,sizeof out));
    failure=1;
    assert(rpi5_provider_refresh(&provider)==RPI5_REFRESH_HEALTH_FAILURE);
    assert(provider.failed && reads==2);
    memset(out,0xa5,sizeof out);
    assert(rpi5_provider_generate(&provider,0,out,sizeof out)==-1);
    assert(rpi5_provider_mix(&provider,seed,64)==-1);
    assert(rpi5_provider_initgen(&provider,2)==-1);
    assert(rpi5_provider_refresh(&provider)==RPI5_REFRESH_HEALTH_FAILURE && reads==2);
    for(unsigned i=0;i<32;i++) assert(out[i]==0xa5);
    for(unsigned i=0;i<4;i++) for(size_t j=0;j<sizeof provider.generators[i].drbg;j++)
        assert(((unsigned char *)&provider.generators[i].drbg)[j]==0);
    /* Simulate a terminal generator inconsistency after an earlier generator
     * has already been reseeded. Refresh must fail and erase the entire set. */
    static struct rpi5_prng_provider inconsistent;
    failure=0;
    assert(!rpi5_provider_init(&inconsistent,4,seed,&ops,entropy,0));
    rpi5_prng_generator_fail(&inconsistent.generators[2]);
    assert(rpi5_provider_refresh(&inconsistent)==RPI5_REFRESH_SOURCE_FAILURE);
    assert(inconsistent.failed);
    for(unsigned i=0;i<4;i++) for(size_t j=0;j<sizeof inconsistent.generators[i].drbg;j++)
        assert(((unsigned char *)&inconsistent.generators[i].drbg)[j]==0);
    assert(!pthread_mutex_destroy(&mutex));
}
'''
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                *[str(ROOT/'osfmk/prng'/u) for u in ('rpi5_prng_provider.c','rpi5_prng_refresh.c','rpi5_prng_generator.c')],
                *[str(lib/'src'/u) for u in ('rand/hmac_drbg.c','mac/hmac.c','hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
