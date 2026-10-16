/* SPDX-License-Identifier: BSD-2-Clause */
#include <kern/startup.h>
#include <kern/cpu_number.h>
#include <kern/misc_protos.h>
#include <libkern/crypto/crypto_internal.h>
#include "rpi5_crypto_table.h"

/* Candidate coordinator, not selected and no STARTUP hook. Intended caller
 * is the boot thread after SYSCTL startup and before PE_init_iokit; earlier
 * consumer auditing must be finished before adding that call site. */
void rpi5_prng_platform_start(void);
void rpi5_crypto_platform_start(void);
void
rpi5_crypto_platform_start(void)
{
    if(cpu_number()!=boot_cpu_id || startup_phase<STARTUP_SUB_SYSCTL ||
        startup_phase>=STARTUP_SUB_EARLY_BOOT || crypto_init || g_crypto_funcs) {
        panic("BCM2712: invalid crypto coordinator startup order");
    }
    if(register_crypto_functions(&rpi5_crypto_functions)) {
        panic("BCM2712: crypto table registration failed");
    }
    /* entropy_init inside PRNG registration uses SHA-512 through the table. */
    rpi5_prng_platform_start();
}
