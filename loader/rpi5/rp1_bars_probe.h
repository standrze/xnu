/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_BARS_PROBE_H
#define RPI5_RP1_BARS_PROBE_H
#include "rp1_config_snapshot.h"

enum rpi5_rp1_bars_state {
    RPI5_RP1_BARS_EMPTY, RPI5_RP1_BARS_CHECKING, RPI5_RP1_BARS_PROBING,
    RPI5_RP1_BARS_RESTORING, RPI5_RP1_BARS_VERIFYING,
    RPI5_RP1_BARS_COMPLETE, RPI5_RP1_BARS_FAILED
};
struct rpi5_rp1_bars_probe {
    enum rpi5_rp1_bars_state state;
    uint32_t selected, originals[6], transactions, writes_started;
};
struct rpi5_rp1_bar_size { uint32_t original, mask, size; };
struct rpi5_rp1_bars_size {
    struct rpi5_rp1_bar_size bar[6];
    uint32_t present, command, transactions;
};

/* The narrowly admitted endpoint writes are six standard BAR size probes and
 * exact restorations. No command, ROM, BAR assignment or memory access. The
 * all-slot inventory is needed because COMMAND.MEM enables every implemented
 * memory BAR, not just BAR1. Only non-prefetchable MEM32 is supported; a zero
 * mask is unimplemented only with original zero. No size inferred from FDT.
 *
 * Same retained snapshot, exclusive owner, real config engine and independently
 * held controller/PM/IRQ/firmware containment are required throughout. The
 * provider uses write_allowed and terminally quarantines on failure: a posted
 * write may have completed. No retry or speculative cleanup, output unchanged.
 * Completion proves size/restoration only, not allocation/decode/Device/DMA.
 * Inputs/session/output are stable, disjoint and session initially zeroed. */
int rpi5_rp1_bars_write_allowed(const struct rpi5_rp1_bars_probe *,
    const struct rpi5_pcie_config_request *);
int rpi5_rp1_bars_probe(struct rpi5_rp1_bars_probe *, struct rpi5_pcie_config *,
    const struct rpi5_rp1_config_snapshot *, struct rpi5_rp1_bars_size *);
#endif
