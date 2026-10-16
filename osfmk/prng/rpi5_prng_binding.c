/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_prng_binding.h"
static struct cckprng_ctx token;
static struct rpi5_prng_provider provider;
static struct rpi5_prng_lock mutex;
static unsigned prepared;
static void check(struct cckprng_ctx *ctx)
{
    if(!prepared || ctx!=&token) rpi5_prng_binding_panic("invalid PRNG binding context");
}
int rpi5_prng_binding_prepare(const struct rpi5_prng_lock *lock)
{
    if(prepared || !lock || !lock->lock || !lock->try_lock || !lock->unlock) return -1;
    mutex=*lock; prepared=1; return 0;
}
struct cckprng_ctx *rpi5_prng_binding_context(void) { return &token; }
static void initialize(struct cckprng_ctx *ctx,unsigned count,size_t seed_size,const void *seed,
    size_t nonce_size,const void *nonce,cckprng_getentropy entropy,void *arg)
{
    check(ctx);
    if(provider.initialized || provider.failed || seed_size!=64 || !seed ||
        nonce_size!=8 || !nonce || !entropy || !count || count>RPI5_PRNG_MAX_GENERATORS)
        rpi5_prng_binding_panic("invalid PRNG initialization contract");
    /* Pinned XNU supplies a 64-byte seed and an 8-byte timebase nonce. The
     * nonce personalizes the state but is never counted as entropy. */
    static const char label[]="rpi5-xnu/kernel-prng/v1";
    br_hmac_key_context key; br_hmac_context hmac; unsigned char derived[64];
    br_hmac_key_init(&key,&br_sha512_vtable,seed,seed_size);
    br_hmac_init(&hmac,&key,64);
    br_hmac_update(&hmac,label,sizeof label-1);
    br_hmac_update(&hmac,nonce,nonce_size);
    (void)br_hmac_out(&hmac,derived);
    int result=rpi5_provider_init(&provider,count,derived,&mutex,entropy,arg);
    for(size_t i=0;i<sizeof derived;i++) ((volatile unsigned char *)derived)[i]=0;
    for(size_t i=0;i<sizeof key;i++) ((volatile unsigned char *)&key)[i]=0;
    for(size_t i=0;i<sizeof hmac;i++) ((volatile unsigned char *)&hmac)[i]=0;
    if(result) rpi5_prng_binding_panic("PRNG initialization failed");
}
static void initgen(struct cckprng_ctx *ctx,unsigned id)
{
    check(ctx);
    if(rpi5_provider_initgen(&provider,id)) rpi5_prng_binding_panic("PRNG initgen failed");
}
static void generate(struct cckprng_ctx *ctx,unsigned id,size_t n,void *out)
{
    check(ctx);
    if(rpi5_provider_generate(&provider,id,out,n)) rpi5_prng_binding_panic("PRNG generation failed");
}
static void reseed(struct cckprng_ctx *ctx,size_t n,const void *seed)
{
    check(ctx);
    /* XNU also exposes this callback to user writes: no fresh-entropy credit. */
    if(rpi5_provider_mix(&provider,seed,n)) rpi5_prng_binding_panic("PRNG seed mixing failed");
}
static void refresh(struct cckprng_ctx *ctx)
{
    check(ctx);
    if(rpi5_provider_refresh(&provider)<0) rpi5_prng_binding_panic("PRNG entropy refresh failed");
}
const struct cckprng_funcs rpi5_prng_binding_functions={
    .initgen=initgen,.reseed=reseed,.refresh=refresh,.generate=generate,
    .init_with_getentropy=initialize
};
