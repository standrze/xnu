/* SPDX-License-Identifier: BSD-2-Clause */
/* Only the new private arm_init overlay includes this implementation. */
#include "arm64/rpi5_reservation_kernel.h"
#include "arm64/rpi5_reservation_api.h"
#include "loader/rpi5/firmware_seed.h"
#include "loader/rpi5/fdt.h"
#include <corecrypto/ccdigest.h>
#include <corecrypto/ccsha2.h>
static SECURITY_READ_ONLY_LATE(struct rpi5_reservation_record) rpi5_boot_reservations;
static SECURITY_READ_ONLY_LATE(unsigned) rpi5_boot_reservations_ready;
const struct rpi5_reservation_record *rpi5_boot_reservation_record(void)
{return rpi5_boot_reservations_ready?&rpi5_boot_reservations:NULL;}
static int rpi5_boot_reservation_bind(const void *wire,size_t bytes,const void *fdt,size_t fdt_bytes,
    const struct rpi5_reservation_boot_context *context)
{
    if(rpi5_boot_reservations_ready)return -1;
    /* No digest is computed from a live boot secret, even if a malformed
     * caller bypassed the loader's matching post-consume restriction. */
    struct rpi5_fdt_property seed;
    if(rpi5_firmware_seed_select(fdt,fdt_bytes,&seed) || seed.length!=64)return -1;
    for(unsigned i=0;i<64;i++)
        if(((volatile const unsigned char *)fdt)[seed.offset+i])return -1;
    /* Fixed scalar original Apple SHA256 provider, no selector, dynamic
     * allocation, RNG/service initialization or metadata-supplied digest. */
    ccdigest_ctx_decl(CCSHA256_STATE_SIZE,CCSHA256_BLOCK_SIZE,ctx);
    unsigned char digest[CCSHA256_OUTPUT_SIZE];
    ccdigest_init(&ccsha256_ltc_di,ctx);
    ccdigest_update(&ccsha256_ltc_di,ctx,fdt_bytes,fdt);
    ccdigest_final(&ccsha256_ltc_di,ctx,digest);
    return rpi5_reservation_kernel_validate(wire,bytes,fdt,fdt_bytes,context,digest,&rpi5_boot_reservations);
}
