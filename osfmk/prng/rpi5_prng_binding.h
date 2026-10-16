/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PRNG_BINDING_H
#define RPI5_PRNG_BINDING_H
#include <corecrypto/cckprng.h>
#include "rpi5_prng_provider.h"
/* Singleton candidate binding. Prepare once with a live lock before XNU
 * registration; initialization must be single-threaded. No registration hook
 * is installed here. ABI context is an identity token, never overlaid with
 * our differently shaped provider state. */
int rpi5_prng_binding_prepare(const struct rpi5_prng_lock *);
struct cckprng_ctx *rpi5_prng_binding_context(void);
extern const struct cckprng_funcs rpi5_prng_binding_functions;
/* Platform adapter must supply a real nonreturning panic, never a no-op. */
void rpi5_prng_binding_panic(const char *) __attribute__((noreturn));
#endif
