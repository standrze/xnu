/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PRNG_GENERATOR_H
#define RPI5_PRNG_GENERATOR_H
#include "bearssl_rand.h"
#include "bearssl_hmac.h"
#include <stdint.h>
/* Caller zero-initializes once and serializes every operation, including
 * failure, with its generator lock. No internal locking or entropy collection.
 * All caller buffers must be disjoint from this state. */
struct rpi5_prng_generator {
    br_hmac_drbg_context drbg;
    uint64_t requests;
    unsigned initialized,failed;
};
/* Conservative project policy, not a claim of a standards-mandated limit. */
#define RPI5_PRNG_REQUEST_LIMIT (1ULL<<20)
int rpi5_prng_generator_init(struct rpi5_prng_generator *,const uint8_t seed[64],uint32_t id);
int rpi5_prng_generator_generate(struct rpi5_prng_generator *,void *,size_t);
/* Mix untrusted user input without resetting the fresh-entropy request limit. */
int rpi5_prng_generator_mix(struct rpi5_prng_generator *,const void *,size_t);
/* Only a qualified fresh entropy sample may reset that limit. */
int rpi5_prng_generator_reseed(struct rpi5_prng_generator *,const uint8_t seed[64]);
/* Erases generator state and permanently rejects later operations. */
void rpi5_prng_generator_fail(struct rpi5_prng_generator *);
#endif
