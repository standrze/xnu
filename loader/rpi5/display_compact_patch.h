/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_COMPACT_PATCH_H
#define RPI5_DISPLAY_COMPACT_PATCH_H
#include "display_allocation_retained.h"
#define RPI5_COMPACT_WIDTH 96u
#define RPI5_COMPACT_HEIGHT 8u
#define RPI5_COMPACT_STORES 768u
#define RPI5_COMPACT_US 500000u
struct rpi5_display_compact_report {
    uint64_t first_address,last_address,start_us,last_us,deadline_us;
    uint32_t attempted,completed,rows,guard_calls,time_calls,barriers,used;
    int result;
};
struct rpi5_display_compact_ops {
    void *opaque;
    int (*current)(void *);
    int (*now_us)(void *,uint64_t *);
    int (*store32)(void *,uint64_t,uint32_t);
    int (*barrier)(void *);
};
/* Fixed store-only patch at (16,16),96x8,pitch7680. Each48px half contains
 * PI5 sampled at even original Apple font rows, then three8px RGB strips.
 * No reads, release,
 * retry, clears outside patch or unbounded strings. Caller must independently
 * own the same-boot retained descriptor and MMU/cache-off store path.
 * One-shot report; partial stores are never undone and retained until reset. */
int rpi5_display_compact_patch(const struct rpi5_display_retained *,
    const struct rpi5_display_compact_ops *,struct rpi5_display_compact_report *);
uint32_t rpi5_display_compact_pixel(unsigned,unsigned);
#endif

