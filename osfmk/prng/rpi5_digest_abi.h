/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DIGEST_ABI_H
#define RPI5_DIGEST_ABI_H
#include <corecrypto/cchmac.h>
#include <stdbool.h>
#include <string.h>

/* Pinned ccdigest layout: nbits, state, block buffer, unsigned num.
 * Copy scalar fields rather than casting byte pointers to stricter alignment.
 * Callers still supply correctly sized XNU contexts and supported descriptors.
 */
static inline uint64_t rpi5_digest_bits(ccdigest_ctx_t ctx)
{
    uint64_t value; memcpy(&value,ctx->state,sizeof value); return value;
}
static inline void rpi5_digest_set_bits(ccdigest_ctx_t ctx,uint64_t value)
{
    memcpy(ctx->state,&value,sizeof value);
}
static inline unsigned rpi5_digest_num(const struct ccdigest_info *di,ccdigest_ctx_t ctx)
{
    unsigned value;
    memcpy(&value,ctx->state+sizeof(uint64_t)+di->state_size+di->block_size,sizeof value);
    return value;
}
static inline void rpi5_digest_set_num(const struct ccdigest_info *di,ccdigest_ctx_t ctx,unsigned value)
{
    memcpy(ctx->state+sizeof(uint64_t)+di->state_size+di->block_size,&value,sizeof value);
}
static inline void *rpi5_digest_state(ccdigest_ctx_t ctx)
{
    return ctx->state+sizeof(uint64_t);
}
static inline void *rpi5_hmac_outer(const struct ccdigest_info *di,cchmac_ctx_t ctx)
{
    return ctx->b+cc_pad_align(ccdigest_di_size(di));
}

extern const struct ccdigest_info rpi5_sha256_di,rpi5_sha384_di,rpi5_sha512_di;
extern const struct ccdigest_info rpi5_md5_di,rpi5_sha1_di;
#define RPI5_DECLARE_DIGEST(prefix) \
    void prefix##_init(const struct ccdigest_info *,ccdigest_ctx_t); \
    void prefix##_update(const struct ccdigest_info *,ccdigest_ctx_t,size_t,const void *); \
    void prefix##_final(const struct ccdigest_info *,ccdigest_ctx_t,void *); \
    void prefix(const struct ccdigest_info *,unsigned long,const void *,void *)
RPI5_DECLARE_DIGEST(rpi5_sha256_digest);
RPI5_DECLARE_DIGEST(rpi5_sha512_digest);
RPI5_DECLARE_DIGEST(rpi5_digest);
RPI5_DECLARE_DIGEST(rpi5_legacy_digest);
#undef RPI5_DECLARE_DIGEST
void rpi5_hmac_init(const struct ccdigest_info *,cchmac_ctx_t,unsigned long,const void *);
void rpi5_hmac_update(const struct ccdigest_info *,cchmac_ctx_t,unsigned long,const void *);
void rpi5_hmac_final(const struct ccdigest_info *,cchmac_ctx_t,unsigned char *);
void rpi5_hmac(const struct ccdigest_info *,unsigned long,const void *,unsigned long,const void *,unsigned char *);
#endif
