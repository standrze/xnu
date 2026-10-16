/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_DECODE_CYCLE_H
#define RPI5_RP1_DECODE_CYCLE_H
#include "rp1_bars_assign.h"

enum rpi5_rp1_decode_state {
    RPI5_RP1_DECODE_EMPTY, RPI5_RP1_DECODE_CHECKING,
    RPI5_RP1_DECODE_ENABLING, RPI5_RP1_DECODE_ENABLED,
    RPI5_RP1_DECODE_MAPPING, RPI5_RP1_DECODE_MAPPED,
    RPI5_RP1_DECODE_UNMAPPING, RPI5_RP1_DECODE_DISABLING,
    RPI5_RP1_DECODE_COMPLETE, RPI5_RP1_DECODE_QUARANTINED
};
struct rpi5_rp1_decode_cycle;
struct rpi5_rp1_decode_io {
    void *context;
    /* Fresh exact owner/thread/phase/session identity, no device access. */
    int (*current)(void *,const struct rpi5_rp1_decode_cycle *,
        const struct rpi5_rp1_assignment *);
    /* Real owner supplies two bounded Device mappings (0=GEM, 1=clocks).
     * Every call must have fresh existing owner/firmware guards before/after,
     * exact immutable physical-memory-type validation, host-only/no-mapper
     * cache-inhibited mapping and exact physical/virtual length verification.
     * unmap revokes the same owner-held map, never a caller-supplied address.
     * Failure may have completed a mapping/release; no retry or forced cleanup.
     * Neither callback may read/write endpoint registers or enable DMA/IRQs. */
    int (*map)(void *,unsigned,struct rpi5_range);
    int (*unmap)(void *,unsigned,struct rpi5_range);
};
struct rpi5_rp1_decode_cycle {
    enum rpi5_rp1_decode_state state;
    const struct rpi5_rp1_assignment *assignment;
    struct rpi5_rp1_decode_io io;
    struct rpi5_rp1_mapping_candidate geometry;
    uint32_t original_command, transactions, writes_started;
    uint32_t pending_write, pending_map, selected, mapped, unmapped;
};
struct rpi5_rp1_decode_observation {
    uint32_t command_before, command_enabled, command_after;
    uint32_t transactions, writes_started, mapped, unmapped;
    struct rpi5_rp1_mapping_candidate geometry;
};

/* Requires a zero-initialized, unused decode session.
 * Same boot/owner's actual ASSIGNED session; never reconstructed receipts.
 * Stable/disjoint/serialized arguments. Verify complete live header/BAR
 * inventory, write COMMAND as a 16-bit value with MEM alone changed (never
 * STATUS/W1C), reverify inventory, map GEM+clock pages, revoke in reverse
 * order, restore original COMMAND and independently reverify all slots.
 * IO/BME remain zero. No BAR write, NIC register read/write, clock/reset,
 * MSI/IRQ or DMA action. A later caller restores BARs only on complete success.
 * Limits: 34 config transfers, 2 halfword writes, 2 maps and 2 unmaps.
 * Any failure quarantines THIS session and preserves caller output, with no
 * compensating writes/unmaps; current hardware/map state may be partial.
 * Real config callbacks retain their existing acquisition/lifecycle/guard
 * checks. Fresh current() additionally binds this exact decode session.
 */
int rpi5_rp1_decode_run(struct rpi5_rp1_decode_cycle *,
    const struct rpi5_rp1_assignment *,const struct rpi5_rp1_decode_io *,
    struct rpi5_rp1_decode_observation *);
int rpi5_rp1_decode_write_allowed(const struct rpi5_rp1_decode_cycle *,
    const struct rpi5_pcie_config_request *);
int rpi5_rp1_decode_mapping_allowed(const struct rpi5_rp1_decode_cycle *,
    unsigned,struct rpi5_range,unsigned);
#endif
