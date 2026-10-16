/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_GEM_CAPABILITIES_H
#define RPI5_RP1_GEM_CAPABILITIES_H
#include "rp1_gem_identify.h"
#define RPI5_GEM_CAP_WORDS 8u
#define RPI5_GEM_CAP_READ_LIMIT 16u

enum rpi5_gem_cap_state {
    RPI5_GEM_CAP_UNUSED, RPI5_GEM_CAP_READING,
    RPI5_GEM_CAP_COMPLETE, RPI5_GEM_CAP_QUARANTINED
};
struct rpi5_gem_cap_session;
struct rpi5_gem_cap_io {
    void *context;
    /* Fresh exact owner/thread/phase and SAME live identity/decode/assignment
     * and Device maps. In-memory, bounded, non-reentrant; no register access.
     * A completed historical identity receipt is never admission authority. */
    int (*current)(void *,const struct rpi5_gem_cap_session *,
        const struct rpi5_gem_identify *,const struct rpi5_rp1_decode_cycle *);
    /* Exactly one aligned LE32 GEM read with existing firmware/PM/IRQ owner
     * guards before/after. No value publication after a failed post-guard.
     * Real adapter must validate read_allowed and the original Device maps. */
    int (*read)(void *,uint32_t,uint32_t *);
};
struct rpi5_gem_cap_session {
    enum rpi5_gem_cap_state state;
    const struct rpi5_gem_cap_session *self;
    const struct rpi5_gem_identify *identity;
    struct rpi5_gem_cap_io io;
    uint32_t busy,pending,reads,pass,index,offset;
    uint32_t words[2][RPI5_GEM_CAP_WORDS];
    int error;
};
struct rpi5_gem_cap_observation {
    /* MID, DCFG1/2/5/6/8/10/12, exact raw immutable design words. */
    uint32_t raw[RPI5_GEM_CAP_WORDS],reads;
    uint32_t id,revision,bus_width_code,bus_width_bits,queue_mask,queue_count;
    uint32_t dma64,isr_clear_on_read,pcs,rx_packet_buffer,tx_packet_buffer;
    uint32_t rx_packet_address_bits,tsu,lso,cutthrough,high_speed;
    uint32_t type1_screeners,type2_screeners,type2_ethertypes,type2_comparators;
    uint32_t rx_descriptor_prefetch_code,tx_descriptor_prefetch_code;
};
/* Pure decoder. Unknown bus-width codes remain explicit bits=0; no silent
 * Linux fallback to32, DMA addressability, IRQ handling or link-up claim. */
int rpi5_gem_cap_decode(const uint32_t [RPI5_GEM_CAP_WORDS],struct rpi5_gem_cap_observation *);
int rpi5_gem_cap_read_allowed(const struct rpi5_gem_cap_session *,uint32_t);
/* Zero unused session; stable disjoint objects; exact live identity at its
 * second completed MID read (15 pre-clocks+2 MID reads), before its existing
 * 15 post-clock reads. Both Device maps remain held, no concurrent revoke.
 * Two identical eight-read passes; MID must match the live identity. Caller
 * may not commit this result until original post-clock equality completes.
 * No polling, writes,
 * NSR/ISR/statistics reads, PHY management, DMA or IRQ change. Any failed
 * owner/read or changed snapshot quarantines this session, leaves output
 * unchanged and requires caller quarantine without compensating cleanup.
 * Existing enclosing9/10/12/15s limits/65536 owner budgets remain mandatory;
 * this finite core adds no timeout extension or hardware authority. */
int rpi5_gem_cap_run(struct rpi5_gem_cap_session *,const struct rpi5_gem_identify *,
    const struct rpi5_gem_cap_io *,struct rpi5_gem_cap_observation *);
#endif
