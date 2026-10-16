/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FRAMEBUFFER_DESCRIPTOR_H
#define RPI5_FRAMEBUFFER_DESCRIPTOR_H
#include "fdt.h"

enum rpi5_fb_format {
    RPI5_FB_XRGB8888 = 1, RPI5_FB_ARGB8888 = 2,
    RPI5_FB_XBGR8888 = 3, RPI5_FB_ABGR8888 = 4
};
struct rpi5_fb_descriptor {
    struct rpi5_range allocation;
    uint64_t visible_bytes;
    uint32_t width, height, stride, format;
};
struct rpi5_fb_plan {
    struct rpi5_fb_descriptor framebuffer;
    struct rpi5_range retained_pages;
};
/* Exact /chosen/framebuffer@<lowercase physical address>, one declared simplefb
 * globally, explicit 1/2-cell chosen widths, Pi5/BCM2712 root compatibility,
 * no children or unhandled node properties/resources. Metadata phandles are
 * shape-checked only; this helper does not resolve display hardware ownership.
 * Narrow initial 32-bit, <=1080p fixed scanout descriptor only. No mailbox,
 * display programming, access to the described address, or scanout proof.
 * Stable/readable input required, <=1MiB FDT. Output unchanged on failure. */
int rpi5_fb_from_fdt(const void *, size_t, const char *, struct rpi5_fb_descriptor *);
/* Independent geometry check and page-rounded exclusion, NOT a memory mapping
 * or allocation. Caller supplies truthful backing DRAM and every conflicting
 * live/managed/firmware range. Advertised memory alone is a firmware trust
 * contract, not exhaustive ownership proof. Retains full allocation + padding.
 * All outputs atomic. Maximum32 backing/64 occupied ranges, 40-bit physical. */
int rpi5_fb_plan(const struct rpi5_fb_descriptor *, const struct rpi5_range *, size_t,
    const struct rpi5_range *, size_t, struct rpi5_fb_plan *);
/* Original Apple's 32-bit text colors are 0x00RRGGBB. Only XRGB is admitted
 * unchanged: ARGB requires separately proven alpha-ignore/opaque adaptation;
 * BGR requires conversion. This reports eligibility, never initializes video. */
int rpi5_fb_apple_text_compatible(const struct rpi5_fb_descriptor *);
#endif
