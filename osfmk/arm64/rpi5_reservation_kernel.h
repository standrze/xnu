/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RESERVATION_KERNEL_H
#define RPI5_RESERVATION_KERNEL_H
#include "loader/rpi5/reservation_record.h"
struct rpi5_reservation_boot_context {
    uint64_t managed_start,managed_end,loader_start,loader_end;
    uint64_t fdt_pa,fdt_bytes,args_pa,args_bytes,tree_pa,tree_bytes;
    uint64_t top,kernel_start,kernel_end,counter;
};
/* Pure complete record binding. Actual digest must be computed by the kernel
 * from its validated retained original FDT, AFTER the loader erased its seed.
 * Context comes from live boot arguments/image/retained display owner, never
 * from this record or a saved receipt. Output is atomic. */
int rpi5_reservation_kernel_validate(const void *,size_t,const void *,size_t,
    const struct rpi5_reservation_boot_context *,const uint8_t [32],struct rpi5_reservation_record *);
/* Geometry only, not standalone authority. The real provider additionally
 * requires the exact immutable record pointer returned by the kernel API and
 * the retained genuine wired IOBuffer/IODMA ownership of the entire span. */
int rpi5_reservation_kernel_buffer(const struct rpi5_reservation_record *,uint64_t,uint64_t);
#endif
