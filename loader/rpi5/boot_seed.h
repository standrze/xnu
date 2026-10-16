/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOT_SEED_H
#define RPI5_BOOT_SEED_H
#include <stdint.h>
#include <stddef.h>
#define RPI5_BOOT_SEED_BYTES 256
enum rpi5_seed_step { RPI5_SEED_WAIT, RPI5_SEED_WORD, RPI5_SEED_FAULT };
struct rpi5_seed_source {
    void *context;
    /* Bounded, nonblocking callbacks. WORD means one fresh, health-accepted
     * word; WAIT must not consume FIFO data. Hardware qualification and
     * startup/clock/reset ownership are the provider's responsibility. */
    enum rpi5_seed_step (*read)(void *context, uint32_t *word);
    uint64_t (*counter)(void *context);
};
/* Whole-transaction bound; unsigned counter deltas support one wrap. Counter
 * must advance monotonically modulo 2^64; ticks must be < 2^63. A finite poll
 * budget also terminates a stuck counter. Rejects all-zero input to match XNU;
 * nonzero data is not evidence of entropy. Output is unchanged on failure.
 * Caller owns a writable 256-byte output, disjoint from source state; callbacks
 * must not alias/mutate it. This collector cannot qualify an entropy source. */
int rpi5_boot_seed_collect(const struct rpi5_seed_source *source,
    uint64_t ticks, size_t polls, uint8_t out[RPI5_BOOT_SEED_BYTES]);
#endif
