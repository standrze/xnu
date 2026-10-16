/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_prng_provider.h"
static void fail_locked(void *context,enum rpi5_refresh_result reason)
{
    (void)reason;
    struct rpi5_prng_provider *p=context;
    p->failed=1;
    for(unsigned i=0;i<p->count;i++) rpi5_prng_generator_fail(&p->generators[i]);
}
int rpi5_provider_init(struct rpi5_prng_provider *p,unsigned count,const uint8_t seed[64],
    const struct rpi5_prng_lock *mutex,int32_t (*entropy)(size_t *,void *,void *),void *arg)
{
    if(!p || p->initialized || p->failed || !count || count>RPI5_PRNG_MAX_GENERATORS ||
        !seed || !mutex || !mutex->lock || !mutex->try_lock || !mutex->unlock || !entropy) return -1;
    p->count=count; p->mutex=*mutex; p->entropy=entropy; p->entropy_context=arg;
    for(unsigned i=0;i<count;i++) {
        if(rpi5_prng_generator_init(&p->generators[i],seed,i)) {
            fail_locked(p,RPI5_REFRESH_INVALID); return -1;
        }
    }
    p->initialized=1;
    return 0;
}
int rpi5_provider_initgen(struct rpi5_prng_provider *p,unsigned id)
{
    if(!p || !p->initialized || id>=p->count) return -1;
    p->mutex.lock(p->mutex.context);
    int result=-1;
    if(!p->failed && !p->active[id]) { p->active[id]=1; result=0; }
    p->mutex.unlock(p->mutex.context);
    return result;
}
int rpi5_provider_generate(struct rpi5_prng_provider *p,unsigned id,void *out,size_t n)
{
    if(!p || !p->initialized || id>=p->count) return -1;
    p->mutex.lock(p->mutex.context);
    int result=-1;
    if(!p->failed && p->active[id]) result=rpi5_prng_generator_generate(&p->generators[id],out,n);
    p->mutex.unlock(p->mutex.context);
    return result;
}
int rpi5_provider_mix(struct rpi5_prng_provider *p,const void *seed,size_t n)
{
    if(!p || !p->initialized || !seed || !n) return -1;
    p->mutex.lock(p->mutex.context);
    int result=-1;
    if(!p->failed) {
        result=0;
        for(unsigned i=0;i<p->count;i++)
            if(rpi5_prng_generator_mix(&p->generators[i],seed,n)) result=-1;
        if(result) fail_locked(p,RPI5_REFRESH_SOURCE_FAILURE);
    }
    p->mutex.unlock(p->mutex.context);
    return result;
}
static int try_lock(void *context)
{
    struct rpi5_prng_provider *p=context;
    return p->mutex.try_lock(p->mutex.context);
}
static void unlock(void *context)
{
    struct rpi5_prng_provider *p=context;
    p->mutex.unlock(p->mutex.context);
}
static int32_t entropy(size_t *n,void *out,void *context)
{
    struct rpi5_prng_provider *p=context;
    if(p->failed) { *n=0; return -1; }
    return p->entropy(n,out,p->entropy_context);
}
static int reseed_locked(void *context,size_t n,const void *seed)
{
    struct rpi5_prng_provider *p=context;
    if(n!=64 || p->failed) return -1;
    for(unsigned i=0;i<p->count;i++)
        if(rpi5_prng_generator_reseed(&p->generators[i],seed)) {
            return -1;
        }
    return 0;
}
enum rpi5_refresh_result rpi5_provider_refresh(struct rpi5_prng_provider *p)
{
    if(!p || !p->initialized) return RPI5_REFRESH_INVALID;
    const struct rpi5_refresh_ops ops={try_lock,unlock,entropy,reseed_locked,fail_locked};
    return rpi5_prng_refresh(&ops,p,p,p);
}
