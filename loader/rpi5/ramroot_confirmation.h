/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RAMROOT_CONFIRMATION_H
#define RPI5_RAMROOT_CONFIRMATION_H
#include <stdint.h>
#include <stdbool.h>

/* One scalar avoids torn cross-CPU geometry. The mount owns publication;
 * interrupt/callout readers never dereference a mount or acquire a VFS lock.
 * Bits0..7 hold present+node count;8..15 are reserved;16..63 hold bytes.
 */
static inline bool
rpi5_root_confirmation_shape(uint32_t nodes, uint64_t bytes)
{
    return nodes >= 4 && nodes <= 96 && bytes >= 32768 &&
        bytes <= UINT64_C(67108864) && bytes % 16384 == 0;
}

static inline bool
rpi5_root_confirmation_publish(uint64_t *state, uint32_t nodes,
    uint64_t bytes, bool readonly)
{
    if (!state) return false;
    uint64_t value = 0;
    bool valid = readonly && rpi5_root_confirmation_shape(nodes, bytes);
    if (valid) value = (bytes << 16) | ((uint64_t)nodes << 1) | 1;
    __atomic_store_n(state, value, __ATOMIC_RELEASE);
    return valid;
}

static inline bool
rpi5_root_confirmation_snapshot(const uint64_t *state, uint32_t *nodes,
    uint64_t *bytes)
{
    if (!state || !nodes || !bytes) return false;
    uint64_t value = __atomic_load_n(state, __ATOMIC_ACQUIRE);
    uint32_t count = (uint32_t)((value >> 1) & 127);
    uint64_t size = value >> 16;
    if (!(value & 1) || (value & UINT64_C(0xff00)) ||
        !rpi5_root_confirmation_shape(count, size)) return false;
    *nodes = count;
    *bytes = size;
    return true;
}

static inline void
rpi5_root_confirmation_clear(uint64_t *state)
{
    __atomic_store_n(state, 0, __ATOMIC_RELEASE);
}
#endif
