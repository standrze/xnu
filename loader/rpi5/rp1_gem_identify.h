/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_GEM_IDENTIFY_H
#define RPI5_RP1_GEM_IDENTIFY_H
#include "rp1_decode_cycle.h"
#define RPI5_GEM_CLOCK_WORDS 15
#define RPI5_GEM_READ_BOUND (2*RPI5_GEM_CLOCK_WORDS+2)

enum rpi5_gem_stage {
    RPI5_GEM_EMPTY, RPI5_GEM_CLOCK_BEFORE, RPI5_GEM_MID_FIRST,
    RPI5_GEM_MID_SECOND, RPI5_GEM_CLOCK_AFTER, RPI5_GEM_COMPLETE,
    RPI5_GEM_QUARANTINED
};
struct rpi5_gem_identify;
struct rpi5_gem_io {
    void *context;
    /* Actual owner's exact session, thread, phase, mapping and assignment
     * identity. This is NOT a receipt or a replacement for hardware guards. */
    int (*current)(void *, const struct rpi5_gem_identify *,
        const struct rpi5_rp1_decode_cycle *);
    /* Exactly one aligned LE32 read from held map 0=GEM / 1=clocks.
     * Actual adapter must validate read_allowed and both original maps, keep
     * all existing fresh firmware/PM/IRQ guards before/after the dereference,
     * and publish no value after a failing post-guard. No writes or polling. */
    int (*read)(void *, unsigned, uint32_t, uint32_t *);
};
struct rpi5_gem_identify {
    enum rpi5_gem_stage stage;
    const struct rpi5_rp1_decode_cycle *decode;
    struct rpi5_gem_io io;
    uint32_t reads, pending, index, offset, clocks_ready;
    uint32_t before[RPI5_GEM_CLOCK_WORDS], after[RPI5_GEM_CLOCK_WORDS], mid[2];
};
struct rpi5_gem_observation {
    uint32_t clocks[RPI5_GEM_CLOCK_WORDS], mid, system_hz, reads;
};
/* Pure decode of a deliberately narrow inherited clock profile. Register
 * order: SYS CTRL/DIV_INT/SEL, PLL_SYS CS/PWR/FBDIV_INT/FBDIV_FRAC/PRIM.
 * xosc=50MHz; selected/active SYS PLL; integer core 1GHz or 2GHz; stable SYS
 * rate exactly 200MHz. Also ETH CTRL/DIV/SEL, TSU CTRL/DIV/SEL, SYS PLL SEC:
 * enabled TX via SYS secondary divider at125MHz; enabled TSU via xosc at50MHz.
 * No claim of exhaustive clock/reset qualification. */
int rpi5_gem_clock_profile(const uint32_t [RPI5_GEM_CLOCK_WORDS]);
int rpi5_gem_read_allowed(const struct rpi5_gem_identify *, unsigned, uint32_t);
/* Zero, unused session + live DECODE_MAPPED session, before any revoke.
 * Fifteen clock reads, profile check, two MID reads, fifteen repeated reads.
 * No changes to clocks/reset/NCR/PHY/DMA/IRQs or configuration registers.
 * Invalid/changed clocks prevent identification. Invalid MID fails closed.
 * All 32 reads are finite; failures quarantine and leave output untouched.
 * Caller must quarantine its decode session on failure (no unsafe cleanup).
 * This identifies accessible GEM only, not a functioning Ethernet driver. */
int rpi5_gem_identify_run(struct rpi5_gem_identify *,
    const struct rpi5_rp1_decode_cycle *, const struct rpi5_gem_io *,
    struct rpi5_gem_observation *);
#endif
