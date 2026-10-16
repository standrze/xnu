/* SPDX-License-Identifier: BSD-2-Clause */
#include <kern/locks.h>
#include <kern/lock_group.h>
#include <kern/misc_protos.h>
#include <kern/startup.h>
#include <kern/cpu_number.h>
#include <libkern/crypto/crypto.h>
#include <machine/machine_routines.h>
#include <pexpert/arm64/board_config.h>
#include <prng/random.h>
#include "rpi5_prng_binding.h"

/* Candidate only: deliberately not selected in files.arm64 and no STARTUP
 * entry. The caller must first register the complete crypto provider, after
 * PERCPU initialization and before secondary startup/ordinary PRNG consumers.
 * crypto_init is a necessary ordering guard, not proof of table completeness.
 */
_Static_assert(MAX_CPUS <= RPI5_PRNG_MAX_GENERATORS, "PRNG CPU capacity");
static lck_grp_t provider_group;
static lck_mtx_t provider_mutex;
static unsigned platform_started;

static void provider_lock(void *context) { lck_mtx_lock(context); }
static int provider_try_lock(void *context) { return lck_mtx_try_lock(context); }
static void provider_unlock(void *context) { lck_mtx_unlock(context); }

void
rpi5_prng_binding_panic(const char *message)
{
    panic("BCM2712: %s", message);
}

void rpi5_prng_platform_start(void);
void
rpi5_prng_platform_start(void)
{
    if (platform_started || !crypto_init || startup_phase < STARTUP_SUB_PERCPU) {
        panic("BCM2712: invalid PRNG platform startup order");
    }
    /* Registration also checks boot_cpu_id. Enforce it before touching locks
     * or consuming the lazily initialized boot seed. */
    if (cpu_number() != boot_cpu_id) {
        panic("BCM2712: PRNG platform startup on secondary CPU");
    }
    platform_started = 1;
    lck_grp_init(&provider_group, "rpi5-prng", LCK_GRP_ATTR_NULL);
    lck_mtx_init(&provider_mutex, &provider_group, LCK_ATTR_NULL);
    const struct rpi5_prng_lock lock = {
        provider_lock, provider_try_lock, provider_unlock, &provider_mutex
    };
    if (rpi5_prng_binding_prepare(&lock)) {
        panic("BCM2712: PRNG binding preparation failed");
    }
    /* Do not depend on some unrelated earlier consumer to derive boot seeds. */
    (void)early_random();
    register_and_init_prng(rpi5_prng_binding_context(),
        &rpi5_prng_binding_functions);
}
