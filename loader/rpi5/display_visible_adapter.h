/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_VISIBLE_ADAPTER_H
#define RPI5_DISPLAY_VISIBLE_ADAPTER_H
#include "display_visible_patch.h"
/* Only the pinned standalone reset-lineage package is a caller. Invokes the
 * frozen zero-prefix allocator exactly once, then consumes THAT same-boot
 * result under immutable fresh FDT and CPU/cache/owner checks. Returns the
 * allocation status; the separate drawing report must also have result0 for
 * software completion. Neither status proves physical scanout/alpha behavior.
 * No framebuffer reads, release, retry, XNU transfer or post-reset reuse. */
int rpi5_display_visible_run(const void *,size_t,struct rpi5_range,void *,uint64_t,
    uint64_t,struct rpi5_display_allocate_result *,struct rpi5_display_allocate_report *,
    struct rpi5_display_visible_report *);
void rpi5_display_visible_store(uintptr_t,uint32_t);
void rpi5_display_visible_barrier(void);
#endif
