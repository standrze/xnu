/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_MEMORY_TYPE_H
#define RPI5_MEMORY_TYPE_H
#include "ranges.h"
enum rpi5_memory_type { RPI5_MEMORY_UNKNOWN, RPI5_MEMORY_NORMAL, RPI5_MEMORY_DEVICE };
struct rpi5_memory_types {
    struct rpi5_ranges normal, device;
};
/* Validate two sorted, disjoint, 16 KiB-page-aligned lists within 40-bit PA.
 * At least one normal range is required. Cross-type overlap is forbidden.
 * No ownership, cache-coherency, or firmware truth is inferred from validation. */
int rpi5_memory_types_validate(const struct rpi5_memory_types *types);
/* Return type only if the entire nonempty range is covered by that type.
 * Adjacent same-type intervals may jointly cover it. Mixed types, holes,
 * malformed maps and invalid queries return UNKNOWN, not DEVICE by default. */
enum rpi5_memory_type rpi5_memory_type_for(const struct rpi5_memory_types *types,
    struct rpi5_range query);
/* rpi5-memory-map v1: LE32 version, LE32 record count, then records of
 * LE64 type (1 normal, 2 device), LE64 start, LE64 exclusive end. Normal
 * records precede device records; each class is sorted. Missing addresses
 * are UNKNOWN, never implicitly device. This describes type, not ownership.
 * Caller supplies disjoint input/output/written objects. Failure preserves
 * output and written; capacity may exceed the exact encoded length. */
#define RPI5_MEMORY_MAP_MAX_BYTES (8u + 64u * 24u)
int rpi5_memory_types_encode(const struct rpi5_memory_types *types,
    void *output, size_t capacity, size_t *written);
#endif
