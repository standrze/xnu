/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_prng_generator.h"
static void wipe(void *p,size_t n)
{
    volatile unsigned char *v=p; while(n--) *v++=0;
}
int rpi5_prng_generator_init(struct rpi5_prng_generator *g,const uint8_t seed[64],uint32_t id)
{
    if(!g || !seed || g->initialized || g->failed) return -1;
    /* Separate generator streams using an explicit label and LE32 identifier.
     * The source is qualified by the caller; derivation creates no entropy. */
    static const char label[]="rpi5-xnu/generator/v1";
    unsigned char derived[32],encoded_id[4];
    for(unsigned i=0;i<4;i++) encoded_id[i]=(unsigned char)(id>>(8*i));
    br_hmac_key_context key; br_hmac_context hmac;
    br_hmac_key_init(&key,&br_sha256_vtable,seed,64);
    br_hmac_init(&hmac,&key,32);
    br_hmac_update(&hmac,label,sizeof label-1);
    br_hmac_update(&hmac,encoded_id,sizeof encoded_id);
    (void)br_hmac_out(&hmac,derived);
    br_hmac_drbg_init(&g->drbg,&br_sha256_vtable,derived,sizeof derived);
    g->requests=0; g->initialized=1;
    wipe(derived,sizeof derived); wipe(&hmac,sizeof hmac); wipe(&key,sizeof key);
    return 0;
}
int rpi5_prng_generator_generate(struct rpi5_prng_generator *g,void *out,size_t n)
{
    if(!g || !g->initialized || g->failed || !out || !n || n>256 ||
        g->requests>=RPI5_PRNG_REQUEST_LIMIT) return -1;
    br_hmac_drbg_generate(&g->drbg,out,n); g->requests++;
    return 0;
}
int rpi5_prng_generator_mix(struct rpi5_prng_generator *g,const void *seed,size_t n)
{
    if(!g || !g->initialized || g->failed || !seed || !n) return -1;
    br_hmac_drbg_update(&g->drbg,seed,n);
    return 0;
}
int rpi5_prng_generator_reseed(struct rpi5_prng_generator *g,const uint8_t seed[64])
{
    if(rpi5_prng_generator_mix(g,seed,64)) return -1;
    g->requests=0; return 0;
}
void rpi5_prng_generator_fail(struct rpi5_prng_generator *g)
{
    if(!g) return;
    wipe(&g->drbg,sizeof g->drbg);
    g->requests=0; g->failed=1;
}
