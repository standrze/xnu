/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CRYPTO_HMAC_H
#define RPI5_CRYPTO_HMAC_H
#include <libkern/crypto/register_crypto.h>
size_t rpi5_crypto_hmac_ctx_size(crypto_digest_alg_t);
void rpi5_crypto_hmac_init(crypto_digest_alg_t,void *,size_t,const void *,size_t);
void rpi5_crypto_hmac_update(crypto_digest_alg_t,void *,size_t,const void *,size_t);
void rpi5_crypto_hmac_final_generate(crypto_digest_alg_t,void *,size_t,void *,size_t);
bool rpi5_crypto_hmac_final_verify(crypto_digest_alg_t,void *,size_t,const void *,size_t);
void rpi5_crypto_hmac_generate(crypto_digest_alg_t,const void *,size_t,const void *,size_t,void *,size_t);
bool rpi5_crypto_hmac_verify(crypto_digest_alg_t,const void *,size_t,const void *,size_t,const void *,size_t);
#endif
