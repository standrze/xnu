/* SPDX-License-Identifier: BSD-2-Clause */
#include "boot_video.h"
static void video_put64(uint8_t *p, uint64_t value)
{
    for (unsigned i = 0; i < 8; i++) p[i] = (uint8_t)(value >> (8 * i));
}
int rpi5_boot_video_encode(const struct rpi5_boot_args_input *input,
    const char *command, size_t length, const struct rpi5_fb_descriptor *framebuffer,
    const struct rpi5_range *ram, size_t ram_count,
    const struct rpi5_range *occupied, size_t occupied_count,
    void *output, size_t capacity)
{
    if (!input || !output || capacity < RPI5_BOOT_ARGS_SIZE) return -1;
    struct rpi5_boot_args_input args = *input;
    struct rpi5_fb_plan plan;
    if (rpi5_fb_plan(framebuffer, ram, ram_count, occupied, occupied_count, &plan) ||
        !rpi5_fb_apple_text_compatible(&plan.framebuffer)) return -1;
    uint8_t bytes[RPI5_BOOT_ARGS_SIZE];
    if (rpi5_boot_args_encode(&args, command, length, bytes, sizeof(bytes))) return -1;
    if (plan.retained_pages.start < args.top &&
        args.phys_base < plan.retained_pages.end) return -1;
    /* Exact upstream LP64 Boot_Video ABI, independently asserted by the tests.
     * Low bit explicitly denotes physical even if console setup occurs late. */
    video_put64(bytes + 40, plan.framebuffer.allocation.start | 1u);
    video_put64(bytes + 48, 0); /* kPETextMode, not graphics progress UI */
    video_put64(bytes + 56, plan.framebuffer.stride);
    video_put64(bytes + 64, plan.framebuffer.width);
    video_put64(bytes + 72, plan.framebuffer.height);
    video_put64(bytes + 80, 32); /* depth=32, rotations=0, encoded scale=0 (1x) */
    uint8_t *destination = output;
    for (size_t i = 0; i < sizeof(bytes); i++) destination[i] = bytes[i];
    return 0;
}
