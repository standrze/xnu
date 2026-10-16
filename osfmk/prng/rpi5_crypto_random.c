/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_crypto_random.h"
#include "rpi5_ccrng.h"
#include <bearssl_rand.h>
#include <stdint.h>

/* Kmem-only state: caller serializes access. Not a substitute for the
 * reseeded ordinary kernel PRNG. Generation never locks or allocates. */
struct kmem_rng {
    br_hmac_drbg_context drbg;
    uint64_t magic;
};
#define KMEM_MAGIC UINT64_C(0x727069356b6d656d)
_Static_assert(sizeof(struct kmem_rng) <= CRYPTO_RANDOM_MAX_CTX_SIZE, "kmem size");
_Static_assert(_Alignof(struct kmem_rng) <= _Alignof(void *), "kmem alignment");
static void wipe(void *p, size_t n) {
    volatile unsigned char *v=p;
    while(n--) *v++=0;
}
static struct kmem_rng *checked(crypto_random_ctx_t ctx) {
    if (!ctx || (uintptr_t)ctx % _Alignof(struct kmem_rng)) __builtin_trap();
    struct kmem_rng *s=ctx;
    if (s->magic != KMEM_MAGIC || s->drbg.vtable != &br_hmac_drbg_vtable ||
        s->drbg.digest_class != &br_sha256_vtable) __builtin_trap();
    return s;
}
static void check_output(struct kmem_rng *s, void *out, size_t n) {
    uintptr_t p=(uintptr_t)out, c=(uintptr_t)s;
    if ((n && !out) || n > UINTPTR_MAX-p ||
        (n && p < c+sizeof *s && c < p+n)) __builtin_trap();
}
size_t rpi5_crypto_random_kmem_ctx_size(void) { return sizeof(struct kmem_rng); }
void rpi5_crypto_random_kmem_init(crypto_random_ctx_t ctx) {
    if (!ctx || (uintptr_t)ctx % _Alignof(struct kmem_rng)) __builtin_trap();
    unsigned char seed[32];
    struct ccrng_state *rng=rpi5_ccrng(NULL);
    if (ccrng_generate(rng,sizeof seed,seed)) __builtin_trap();
    struct kmem_rng *s=ctx;
    br_hmac_drbg_init(&s->drbg,&br_sha256_vtable,seed,sizeof seed);
    s->magic=KMEM_MAGIC;
    wipe(seed,sizeof seed);
}
void rpi5_crypto_random_generate(crypto_random_ctx_t ctx, void *out, size_t n) {
    struct kmem_rng *s=checked(ctx);
    check_output(s,out,n);
    if (n) br_hmac_drbg_generate(&s->drbg,out,n);
}
void rpi5_crypto_random_uniform(crypto_random_ctx_t ctx, uint64_t bound, uint64_t *out) {
    struct kmem_rng *s=checked(ctx);
    check_output(s,out,sizeof *out);
    if (!bound || (uintptr_t)out % _Alignof(uint64_t)) __builtin_trap();
    /* Reject the short residue interval so every result has equal weight. */
    uint64_t threshold=(UINT64_C(0)-bound)%bound, value;
    do {
        br_hmac_drbg_generate(&s->drbg,&value,sizeof value);
    } while (value < threshold);
    *out=value%bound;
    wipe(&value,sizeof value);
}
