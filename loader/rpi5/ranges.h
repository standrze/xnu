/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RANGES_H
#define RPI5_RANGES_H
#include <stddef.h>
#include <stdint.h>
struct rpi5_range { uint64_t start, end; };
struct rpi5_ranges { struct rpi5_range extent[32]; size_t count; };
/* Validate disjoint live ranges wholly covered by sorted advertised RAM.
 * Adjacent RAM banks may jointly cover a live range. No ownership proof. */
int rpi5_ranges_validate_live(const struct rpi5_range *ram, size_t nr,
    const struct rpi5_range *live, size_t nl);
/* RAM must be sorted/non-overlapping. Exclusions may overlap or be unordered.
 * All inputs must be valid 40-bit half-open ranges; at most 32 RAM/64 exclusions.
 * Atomic output; -1 for invalid input or output fragmentation beyond capacity.
 * Caller must supply ALL reservations/live allocations; no ownership discovery. */
int rpi5_ranges_subtract(const struct rpi5_range *ram, size_t nr,
    const struct rpi5_range *excluded, size_t ne, struct rpi5_ranges *out);
/* Lowest-address aligned fit in available RAM intersected with allowed windows.
 * Pure placement, no allocation/memory write; caller must reserve a returned fit.
 * Explicit nonempty windows, power-of-two alignment; output unchanged on failure. */
int rpi5_ranges_find(const struct rpi5_ranges *available,
    const struct rpi5_range *windows, size_t nw, uint64_t size,
    uint64_t alignment, struct rpi5_range *out);
#endif
