# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class PrngRefreshTests(unittest.TestCase):
    def test_real_mutex_contention(self):
        code=r'''
#include "rpi5_prng_refresh.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <string.h>
static pthread_mutex_t provider=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t sync_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static int entered,release_worker;
static atomic_uint reads,reseeds;
static int lock(void *p) {
    int r=pthread_mutex_trylock(p);
    assert(r==0 || r==EBUSY); return r==0;
}
static void unlock(void *p) { assert(!pthread_mutex_unlock(p)); }
static int32_t entropy(size_t *n,void *p,void *arg) {
    (void)arg; assert(*n==64); memset(p,0x5a,64); *n=64;
    atomic_fetch_add(&reads,1); return 576;
}
static int reseed(void *p,size_t n,const void *seed) {
    (void)p; assert(n==64);
    for(size_t i=0;i<n;i++) assert(((const unsigned char *)seed)[i]==0x5a);
    atomic_fetch_add(&reseeds,1);
    assert(!pthread_mutex_lock(&sync_lock));
    entered=1; assert(!pthread_cond_broadcast(&condition));
    while(!release_worker) assert(!pthread_cond_wait(&condition,&sync_lock));
    assert(!pthread_mutex_unlock(&sync_lock));
    return 0;
}
static void failure(void *p,enum rpi5_refresh_result r) { (void)p; (void)r; assert(0); }
static const struct rpi5_refresh_ops ops={lock,unlock,entropy,reseed,failure};
static void *worker(void *p) {
    (void)p;
    assert(rpi5_prng_refresh(&ops,&provider,0,0)==RPI5_REFRESH_RESEEDED);
    return 0;
}
int main(void) {
    pthread_t thread;
    assert(!pthread_create(&thread,0,worker,0));
    assert(!pthread_mutex_lock(&sync_lock));
    while(!entered) assert(!pthread_cond_wait(&condition,&sync_lock));
    assert(!pthread_mutex_unlock(&sync_lock));
    /* Worker cannot finish until this thread releases it. A blocking refresh
     * deadlocks here and is caught by the subprocess timeout, without sleeps. */
    for(unsigned i=0;i<1000;i++)
        assert(rpi5_prng_refresh(&ops,&provider,0,0)==RPI5_REFRESH_BUSY);
    assert(atomic_load(&reads)==1 && atomic_load(&reseeds)==1);
    assert(!pthread_mutex_lock(&sync_lock));
    release_worker=1; assert(!pthread_cond_broadcast(&condition));
    assert(!pthread_mutex_unlock(&sync_lock));
    assert(!pthread_join(thread,0));
    assert(rpi5_prng_refresh(&ops,&provider,0,0)==RPI5_REFRESH_RESEEDED);
    assert(atomic_load(&reads)==2 && atomic_load(&reseeds)==2);
    assert(!pthread_mutex_destroy(&provider));
    assert(!pthread_mutex_destroy(&sync_lock));
    assert(!pthread_cond_destroy(&condition));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_prng_refresh.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)

    def test_callback_order_results_and_erasure(self):
        code=r'''
#include "rpi5_prng_refresh.h"
#include <assert.h>
#include <string.h>
static unsigned locks,unlocks,reads,reseeded,held,busy,failures;
static int32_t samples;
static size_t returned;
static const unsigned char *scratch;
static int lock(void *p) { assert(p==(void *)1); locks++; if(busy)return 0; held=1; return 1; }
static void unlock(void *p) {
    assert(p==(void *)1 && held && scratch);
    assert(failures==(samples<0 || (samples==0 && returned!=0) || (samples>0 && returned!=64)));
    for(unsigned i=0;i<64;i++) assert(scratch[i]==0);
    held=0; unlocks++;
}
static int32_t entropy(size_t *n,void *p,void *arg) {
    assert(arg==(void *)2 && held && *n==64); reads++; scratch=p;
    for(unsigned i=0;i<64;i++) assert(((unsigned char *)p)[i]==0);
    memset(p,0x5a,64); *n=returned; return samples;
}
static int reseed(void *p,size_t n,const void *data) {
    assert(p==(void *)3 && held && n==64 && samples>0);
    for(unsigned i=0;i<64;i++) assert(((const unsigned char *)data)[i]==0x5a);
    reseeded++;
    return 0;
}
static void failure(void *p,enum rpi5_refresh_result result) {
    assert(p==(void *)3 && held && reads==1 && !unlocks && !reseeded);
    assert(result==(samples<0?RPI5_REFRESH_HEALTH_FAILURE:RPI5_REFRESH_SOURCE_FAILURE));
    failures++;
}
int main(void) {
    const struct rpi5_refresh_ops ops={lock,unlock,entropy,reseed,failure};
    for(unsigned mask=0;mask<31;mask++) {
        struct rpi5_refresh_ops bad=ops;
        if(!(mask&1))bad.try_lock=0;
        if(!(mask&2))bad.unlock=0;
        if(!(mask&4))bad.entropy=0;
        if(!(mask&8))bad.reseed_locked=0;
        if(!(mask&16))bad.failure_locked=0;
        assert(rpi5_prng_refresh(&bad,(void *)1,(void *)2,(void *)3)==RPI5_REFRESH_INVALID);
        assert(!locks);
    }
    busy=1;
    assert(rpi5_prng_refresh(&ops,(void *)1,(void *)2,(void *)3)==RPI5_REFRESH_BUSY);
    assert(locks==1 && !unlocks && !reads && !reseeded);
    busy=0;
    const int32_t counts[]={INT32_MIN,-1,0,1,576,INT32_MAX};
    const size_t lengths[]={0,1,63,64,65,SIZE_MAX};
    for(unsigned i=0;i<6;i++) for(unsigned j=0;j<6;j++) {
        samples=counts[i]; returned=lengths[j];
        locks=unlocks=reads=reseeded=failures=0; scratch=0;
        enum rpi5_refresh_result expected=samples<0?RPI5_REFRESH_HEALTH_FAILURE:
            samples==0 && returned==0?RPI5_REFRESH_EMPTY:
            samples>0 && returned==64?RPI5_REFRESH_RESEEDED:RPI5_REFRESH_SOURCE_FAILURE;
        assert(rpi5_prng_refresh(&ops,(void *)1,(void *)2,(void *)3)==expected);
        assert(locks==1 && unlocks==1 && reads==1 && !held);
        assert(reseeded==(expected==RPI5_REFRESH_RESEEDED));
    }
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_prng_refresh.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
