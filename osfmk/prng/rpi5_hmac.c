/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate HMAC adapter for XNU's context layout, not registered.
 * Input/output/context objects must be disjoint. No allocation or RNG use.
 */
#include <corecrypto/cchmac.h>
#include <string.h>
#include "rpi5_digest_abi.h"
extern const struct ccdigest_info rpi5_sha256_di,rpi5_sha384_di,rpi5_sha512_di;
void rpi5_digest_init(const struct ccdigest_info *,ccdigest_ctx_t);
void rpi5_digest_update(const struct ccdigest_info *,ccdigest_ctx_t,size_t,const void *);
void rpi5_digest_final(const struct ccdigest_info *,ccdigest_ctx_t,void *);
void rpi5_digest(const struct ccdigest_info *,unsigned long,const void *,void *);
static void validate(const struct ccdigest_info *di,const void *ctx)
{
    if(!ctx || (di!=&rpi5_sha256_di && di!=&rpi5_sha384_di && di!=&rpi5_sha512_di &&
        di!=&rpi5_md5_di && di!=&rpi5_sha1_di))
        __builtin_trap();
}
static void clear(void *p,size_t n)
{
    volatile unsigned char *v=p;
    while(n--) *v++=0;
}
void rpi5_hmac_init(const struct ccdigest_info *di,cchmac_ctx_t ctx,
    unsigned long key_length,const void *key)
{
    validate(di,ctx);
    if(key_length && !key) __builtin_trap();
    unsigned char pad[128]={0},hashed[64]={0};
    if(key_length>di->block_size) {
        rpi5_digest(di,key_length,key,hashed);
        memcpy(pad,hashed,di->output_size);
    } else if(key_length) memcpy(pad,key,key_length);
    /* Save the state after the outer pad, then build the inner context. */
    ccdigest_ctx_decl(64,128,outer);
    for(size_t i=0;i<di->block_size;i++) pad[i]^=0x5c;
    rpi5_digest_init(di,outer);
    rpi5_digest_update(di,outer,di->block_size,pad);
    memset(ctx,0,cchmac_di_size(di));
    memcpy(rpi5_hmac_outer(di,ctx),rpi5_digest_state(outer),di->state_size);
    for(size_t i=0;i<di->block_size;i++) pad[i]^=0x5c^0x36;
    rpi5_digest_init(di,cchmac_digest_ctx(di,ctx));
    rpi5_digest_update(di,cchmac_digest_ctx(di,ctx),di->block_size,pad);
    clear(pad,sizeof pad); clear(hashed,sizeof hashed);
    clear(outer,ccdigest_ctx_size(64,128));
}
void rpi5_hmac_update(const struct ccdigest_info *di,cchmac_ctx_t ctx,
    unsigned long length,const void *data)
{
    validate(di,ctx);
    rpi5_digest_update(di,cchmac_digest_ctx(di,ctx),length,data);
}
void rpi5_hmac_final(const struct ccdigest_info *di,cchmac_ctx_t ctx,unsigned char *out)
{
    validate(di,ctx);
    if(!out) __builtin_trap();
    unsigned char inner[64];
    ccdigest_ctx_decl(64,128,outer);
    rpi5_digest_final(di,cchmac_digest_ctx(di,ctx),inner);
    rpi5_digest_init(di,outer);
    memcpy(rpi5_digest_state(outer),rpi5_hmac_outer(di,ctx),di->state_size);
    rpi5_digest_set_bits(outer,di->block_size*8);
    rpi5_digest_update(di,outer,di->output_size,inner);
    rpi5_digest_final(di,outer,out);
    clear(inner,sizeof inner); clear(outer,ccdigest_ctx_size(64,128));
}
void rpi5_hmac(const struct ccdigest_info *di,unsigned long key_length,const void *key,
    unsigned long length,const void *data,unsigned char *out)
{
    validate(di,out);
    if((length && !data) || (key_length && !key)) __builtin_trap();
    cchmac_ctx_decl(64,128,ctx);
    rpi5_hmac_init(di,ctx,key_length,key);
    rpi5_hmac_update(di,ctx,length,data);
    rpi5_hmac_final(di,ctx,out);
    clear(ctx,cchmac_ctx_size(64,128));
}
