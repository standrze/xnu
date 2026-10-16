/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate size-explicit HMAC API; not registered. Local policy requires
 * full-length tags, same algorithm through context lifetime, initialized and
 * disjoint correctly sized context/input/output objects. External caller
 * compatibility is not established by the signatures alone.
 */
#include "rpi5_crypto_hmac.h"
#include "rpi5_crypto_digest.h"
#include "rpi5_digest_abi.h"
static void check_context(const struct ccdigest_info *di,void *ctx,size_t size)
{
    if(!ctx || size<cchmac_di_size(di) ||
        (uintptr_t)ctx % _Alignof(struct cchmac_ctx)) __builtin_trap();
}
static void check_tag(const struct ccdigest_info *di,const void *tag,size_t size)
{
    if(!tag || size!=di->output_size) __builtin_trap();
}
static bool compare_and_clear(unsigned char actual[64],const void *tag,size_t n)
{
    const unsigned char *expected=tag;
    /* Always examine the entire public tag length, irrespective of where a
     * mismatch occurs. No memcmp or early return on secret-dependent bytes. */
    volatile unsigned difference=0;
    for(size_t i=0;i<n;i++) difference|=(unsigned)(actual[i]^expected[i]);
    bool equal=difference==0;
    for(size_t i=0;i<64;i++) ((volatile unsigned char *)actual)[i]=0;
    return equal;
}
size_t rpi5_crypto_hmac_ctx_size(crypto_digest_alg_t alg)
{
    return cchmac_di_size(rpi5_crypto_digest_descriptor(alg));
}
void rpi5_crypto_hmac_init(crypto_digest_alg_t alg,void *ctx,size_t size,const void *key,size_t n)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_context(di,ctx,size); if(n && !key) __builtin_trap();
    rpi5_hmac_init(di,ctx,n,key);
}
void rpi5_crypto_hmac_update(crypto_digest_alg_t alg,void *ctx,size_t size,const void *data,size_t n)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_context(di,ctx,size); if(n && !data) __builtin_trap();
    rpi5_hmac_update(di,ctx,n,data);
}
void rpi5_crypto_hmac_final_generate(crypto_digest_alg_t alg,void *ctx,size_t size,void *tag,size_t n)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_context(di,ctx,size); check_tag(di,tag,n); rpi5_hmac_final(di,ctx,tag);
}
bool rpi5_crypto_hmac_final_verify(crypto_digest_alg_t alg,void *ctx,size_t size,const void *tag,size_t n)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_context(di,ctx,size); check_tag(di,tag,n);
    unsigned char actual[64]={0}; rpi5_hmac_final(di,ctx,actual);
    return compare_and_clear(actual,tag,n);
}
void rpi5_crypto_hmac_generate(crypto_digest_alg_t alg,const void *key,size_t key_size,
    const void *data,size_t data_size,void *tag,size_t tag_size)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_tag(di,tag,tag_size);
    if((key_size && !key) || (data_size && !data)) __builtin_trap();
    rpi5_hmac(di,key_size,key,data_size,data,tag);
}
bool rpi5_crypto_hmac_verify(crypto_digest_alg_t alg,const void *key,size_t key_size,
    const void *data,size_t data_size,const void *tag,size_t tag_size)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(alg);
    check_tag(di,tag,tag_size);
    if((key_size && !key) || (data_size && !data)) __builtin_trap();
    unsigned char actual[64]={0}; rpi5_hmac(di,key_size,key,data_size,data,actual);
    return compare_and_clear(actual,tag,tag_size);
}
