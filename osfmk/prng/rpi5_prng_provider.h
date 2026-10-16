/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PRNG_PROVIDER_H
#define RPI5_PRNG_PROVIDER_H
#include "rpi5_prng_generator.h"
#include "rpi5_prng_refresh.h"
#define RPI5_PRNG_MAX_GENERATORS 64
struct rpi5_prng_lock {
    void (*lock)(void *);
    int (*try_lock)(void *);
    void (*unlock)(void *);
    void *context;
};
struct rpi5_prng_provider {
    struct rpi5_prng_generator generators[RPI5_PRNG_MAX_GENERATORS];
    unsigned active[RPI5_PRNG_MAX_GENERATORS];
    unsigned count,initialized,failed;
    struct rpi5_prng_lock mutex;
    int32_t (*entropy)(size_t *,void *,void *);
    void *entropy_context;
};
/* Initialize once, before publication, from zeroed storage. Caller provides
 * an already-initialized lock and qualified seed. No concurrent init/destroy.
 * Buffers must not alias provider storage. Seed is not retained; every stream
 * is instantiated immediately but enabled only by initgen. Not XNU-registered. */
int rpi5_provider_init(struct rpi5_prng_provider *,unsigned,const uint8_t seed[64],
    const struct rpi5_prng_lock *,int32_t (*)(size_t *,void *,void *),void *);
int rpi5_provider_initgen(struct rpi5_prng_provider *,unsigned);
int rpi5_provider_generate(struct rpi5_prng_provider *,unsigned,void *,size_t);
int rpi5_provider_mix(struct rpi5_prng_provider *,const void *,size_t);
enum rpi5_refresh_result rpi5_provider_refresh(struct rpi5_prng_provider *);
#endif
