/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_ALLOCATION_RETAINED_H
#define RPI5_DISPLAY_ALLOCATION_RETAINED_H
#include "display_allocate_adapter.h"
#include "framebuffer_descriptor.h"
struct rpi5_display_retained {
    struct rpi5_fb_descriptor framebuffer;
    struct rpi5_range retained_pages;
    uint64_t fresh_low_ram_end;
};
/* Pure same-boot caller contract, not an unforgeable capability. The actual
 * consumer must own the frozen allocator invocation and immutable fresh FDT.
 * Derive only the exact matched zero-prefix allocation, outside advertised RAM
 * and all fixed/live/initrd/extra occupied ranges. Never widens FDT RAM or the
 * managed span; extra ranges must include the complete future managed span.
 * No allocation, access, mapping, release, boot argument or lifetime transfer.
 * Output unchanged on failure. Retain the full allocation and rounded padding. */
int rpi5_display_allocation_retained(const struct rpi5_display_allocate_result *,
    const struct rpi5_display_allocate_report *,const void *,size_t,uint64_t,
    struct rpi5_range,const struct rpi5_range *,size_t,struct rpi5_display_retained *);
#endif
