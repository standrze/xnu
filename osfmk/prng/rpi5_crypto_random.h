/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CRYPTO_RANDOM_H
#define RPI5_CRYPTO_RANDOM_H
#include <libkern/crypto/rand.h>
size_t rpi5_crypto_random_kmem_ctx_size(void);
void rpi5_crypto_random_kmem_init(crypto_random_ctx_t);
void rpi5_crypto_random_generate(crypto_random_ctx_t, void *, size_t);
void rpi5_crypto_random_uniform(crypto_random_ctx_t, uint64_t, uint64_t *);
#endif
