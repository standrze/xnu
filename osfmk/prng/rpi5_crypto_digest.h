/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CRYPTO_DIGEST_H
#define RPI5_CRYPTO_DIGEST_H
#include <libkern/crypto/register_crypto.h>
const struct ccdigest_info *rpi5_crypto_digest_descriptor(crypto_digest_alg_t);
size_t rpi5_crypto_digest_ctx_size(crypto_digest_alg_t);
void rpi5_crypto_digest_init(crypto_digest_alg_t,void *,size_t);
void rpi5_crypto_digest_update(crypto_digest_alg_t,void *,size_t,const void *,size_t);
void rpi5_crypto_digest_final(crypto_digest_alg_t,void *,size_t,void *,size_t);
void rpi5_crypto_digest(crypto_digest_alg_t,const void *,size_t,void *,size_t);
#endif
