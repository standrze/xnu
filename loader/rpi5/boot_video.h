/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOT_VIDEO_H
#define RPI5_BOOT_VIDEO_H
#include "boot_args.h"
#include "framebuffer_descriptor.h"
/* Distinct, opt-in ARM64 boot_args encoder. Revalidates geometry and retained
 * pages against the supplied physical ownership ledger, then uses the original
 * headless encoder. Only its six Boot_Video fields differ on success.
 * XRGB8888/text/no rotation/scale 1 only. v_baseAddr carries Apple's physical
 * address bit; it is NOT a kernel VA. Output is unchanged on any failure.
 *
 * This does not establish scanout, program display hardware, allocate/map/cache
 * memory, or publish console readiness. Caller must preserve the full rounded
 * allocation and supply truthful RAM/live ranges from the same boot epoch.
 * The entire bootstrap [phys_base, top) reservation is additionally excluded.
 * The subsequent kernel mapping and scanout/cache contract remain mandatory.
 */
int rpi5_boot_video_encode(const struct rpi5_boot_args_input *, const char *, size_t,
    const struct rpi5_fb_descriptor *, const struct rpi5_range *, size_t,
    const struct rpi5_range *, size_t, void *, size_t);
#endif
