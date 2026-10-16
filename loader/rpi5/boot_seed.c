/* SPDX-License-Identifier: BSD-2-Clause */
#include "boot_seed.h"

int rpi5_boot_seed_collect(const struct rpi5_seed_source *source,
    uint64_t ticks, size_t polls, uint8_t out[RPI5_BOOT_SEED_BYTES])
{
    if (!source || !source->read || !source->counter || !out ||
        !ticks || ticks >= (1ull << 63) || !polls) return -1;
    struct rpi5_seed_source s = *source;
    volatile uint8_t scratch[RPI5_BOOT_SEED_BYTES] = {0};
    uint32_t word = 0;
    uint32_t nonzero = 0;
    size_t used = 0;
    int result = -1;
    uint64_t start = s.counter(s.context);
    while (polls--) {
        if (s.counter(s.context) - start >= ticks) break;
        enum rpi5_seed_step step = s.read(s.context, &word);
        /* Include callback duration in the same deadline. No partial publish
         * even when the final word arrives at or after the deadline. */
        if (s.counter(s.context) - start >= ticks) break;
        if (step == RPI5_SEED_WAIT) continue;
        if (step != RPI5_SEED_WORD) break;
        nonzero |= word;
        for (unsigned i = 0; i < 4; ++i)
            scratch[used++] = (uint8_t)(word >> (8 * i));
        word = 0;
        if (used == RPI5_BOOT_SEED_BYTES) {
            /* Match XNU's all-null seed rejection. This is only a gross
             * invalid-data check, not an entropy estimate or health test. */
            if (!nonzero) break;
            for (size_t i = 0; i < used; ++i) out[i] = scratch[i];
            result = 0;
            break;
        }
    }
    /* Volatile stores prevent removal of scratch clearing. This does not
     * claim erasure of compiler register spills or the provider's own state. */
    for (size_t i = 0; i < sizeof scratch; ++i) scratch[i] = 0;
    word = 0;
    return result;
}
