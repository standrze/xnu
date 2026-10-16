/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate size-explicit digest API. No registration yet.
 * Local contract: supported algorithm, context capacity >= reported size,
 * exact digest output size, disjoint input/output/context buffers. Invalid
 * contracts trap before writing. Caller initializes before update/final and
 * retains the same algorithm throughout a context's lifetime.
 */
#include "rpi5_crypto_digest.h"
#include "rpi5_digest_abi.h"
const struct ccdigest_info *rpi5_crypto_digest_descriptor(crypto_digest_alg_t algorithm)
{
    switch(algorithm) {
    case CRYPTO_DIGEST_ALG_MD5: return &rpi5_md5_di;
    case CRYPTO_DIGEST_ALG_SHA1: return &rpi5_sha1_di;
    case CRYPTO_DIGEST_ALG_SHA256: return &rpi5_sha256_di;
    case CRYPTO_DIGEST_ALG_SHA384: return &rpi5_sha384_di;
    case CRYPTO_DIGEST_ALG_SHA512: return &rpi5_sha512_di;
    default: __builtin_trap();
    }
}
static void check_context(const struct ccdigest_info *di,void *ctx,size_t size)
{
    if(!ctx || size<ccdigest_di_size(di) ||
        (uintptr_t)ctx % _Alignof(struct ccdigest_ctx)) __builtin_trap();
}
size_t rpi5_crypto_digest_ctx_size(crypto_digest_alg_t algorithm)
{
    return ccdigest_di_size(rpi5_crypto_digest_descriptor(algorithm));
}
void rpi5_crypto_digest_init(crypto_digest_alg_t algorithm,void *ctx,size_t size)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(algorithm);
    check_context(di,ctx,size); rpi5_digest_init(di,ctx);
}
void rpi5_crypto_digest_update(crypto_digest_alg_t algorithm,void *ctx,size_t size,
    const void *data,size_t length)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(algorithm);
    check_context(di,ctx,size);
    if(length && !data) __builtin_trap();
    rpi5_digest_update(di,ctx,length,data);
}
void rpi5_crypto_digest_final(crypto_digest_alg_t algorithm,void *ctx,size_t size,
    void *out,size_t out_size)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(algorithm);
    check_context(di,ctx,size);
    if(!out || out_size!=di->output_size) __builtin_trap();
    rpi5_digest_final(di,ctx,out);
}
void rpi5_crypto_digest(crypto_digest_alg_t algorithm,const void *data,size_t length,
    void *out,size_t out_size)
{
    const struct ccdigest_info *di=rpi5_crypto_digest_descriptor(algorithm);
    if(!out || out_size!=di->output_size || (length && !data)) __builtin_trap();
    rpi5_digest(di,length,data,out);
}
