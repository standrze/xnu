/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RESERVATION_RECORD_H
#define RPI5_RESERVATION_RECORD_H
#include "fdt.h"
#define RPI5_RESERVATION_RECORD_BYTES 1056u
#define RPI5_RESERVATION_RECORD_PROPERTY "rpi5-resolved-reservations-v1"
#define RPI5_RESERVATION_RECORD_MAGIC UINT64_C(0x3156534552565352)
struct rpi5_reservation_claim {
    uint64_t node_offset, no_map, start, end, alignment;
};
struct rpi5_reservation_record {
    uint64_t fixed_count, dynamic_count;
    uint64_t managed_start, managed_end, loader_start, loader_end;
    uint64_t fdt_pa, fdt_bytes, args_pa, args_bytes, tree_pa, tree_bytes;
    uint64_t top, kernel_start, kernel_end, owner_counter;
    uint8_t fdt_sha256[32];
    struct rpi5_range fixed[32];
    struct rpi5_reservation_claim dynamic[8];
};
/* Version1 deliberately retains the original FDT IN PLACE: fdt_pa is both
 * the resolver's original live extent and the kernel retained descriptor.
 * Relocation requires a new schema, not an inferred historical address.
 * These are loader-resolved EXCLUSIONS, not a firmware allocation/release or
 * a permission to reclaim any reservation. Every exclusion is outside the
 * unchanged managed[0x6000000,0x10000000) span. The kernel must independently
 * bind all metadata to live BootArgs/retained descriptor, compare genuine
 * SHA256 of actual original FDT bytes AFTER firmware rng-seed erasure, and
 * honor exclusions before use. No pre-erasure digest may be produced.
 * Ownercounter is context only, never an authenticated capability. */
int rpi5_reservation_record_valid(const struct rpi5_reservation_record *);
int rpi5_reservation_record_encode(const struct rpi5_reservation_record *,void *,size_t);
int rpi5_reservation_record_decode(const void *,size_t,struct rpi5_reservation_record *);
/* Decode the actual original reservation plan, augment EXACTLY as the frozen
 * runtime loader does: protect firmware[0,0x80000) and original foreign initrd.
 * No allocation/commit or memory access through recorded physical addresses. */
int rpi5_reservation_record_source(const void *,size_t,struct rpi5_fdt_memory *,struct rpi5_reservation_plan *);
/* Exact canonical fixed union and one-to-one dynamic request binding against
 * fresh original FDT. SHA implementation is intentionally caller-owned; this
 * does NOT accept a metadata-supplied digest as actual source verification.
 * Stable disjoint input/output objects required. Atomic outputs on failure. */
int rpi5_reservation_record_validate_fdt(const struct rpi5_reservation_record *,const void *,size_t);
int rpi5_reservation_record_fixed(const struct rpi5_reservation_plan *,struct rpi5_ranges *);
#endif
