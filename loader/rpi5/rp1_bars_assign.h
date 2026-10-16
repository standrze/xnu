/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_BARS_ASSIGN_H
#define RPI5_RP1_BARS_ASSIGN_H
#include "rp1_bars_plan.h"

enum rpi5_rp1_assignment_state {
    RPI5_RP1_ASSIGN_EMPTY, RPI5_RP1_ASSIGN_CHECKING,
    RPI5_RP1_ASSIGN_WRITING, RPI5_RP1_ASSIGN_VERIFYING,
    RPI5_RP1_ASSIGN_ASSIGNED, RPI5_RP1_ASSIGN_RESTORING,
    RPI5_RP1_ASSIGN_RESTORED, RPI5_RP1_ASSIGN_QUARANTINED
};
struct rpi5_rp1_assignment_source {
    void *context;
    /* Fresh in-memory owner/thread/phase and exact-owned-object verification,
     * not a historical token or one-time pointer check. Must be bounded,
     * non-reentrant, read-only and perform no MMIO/SMC/clock/guard operation.
     * The existing config engine/provider still performs fresh hardware guards.
     * context must equal config.io.context; zero means currently owned. */
    int (*current)(void *,const struct rpi5_pcie_config *,const struct rpi5_pcie_fdt *,
        const struct rpi5_rp1_bars_probe *,const struct rpi5_rp1_bars_size *);
};
struct rpi5_rp1_assignment {
    enum rpi5_rp1_assignment_state state;
    struct rpi5_pcie_config *config;
    const struct rpi5_rp1_bars_probe *probe;
    const struct rpi5_rp1_bars_size *sizes;
    const struct rpi5_pcie_fdt *binding;
    struct rpi5_rp1_assignment_source source;
    struct rpi5_rp1_bars_plan plan;
    struct rpi5_pcie_outbound_encoding windows[2];
    uint32_t sizes_saved[6], masks_saved[6];
    uint32_t originals[6], command, selected, transactions, writes_started;
    uint32_t pending_write, assigned_mask, restored_mask;
};
struct rpi5_rp1_assignment_observation {
    uint32_t bar[6], command, transactions, writes_started;
};
struct rpi5_rp1_mapping_candidate {
    struct rpi5_range bar1_cpu, gem_pages, clock_pages;
};

/* A new same-owner, same-boot diagnostic seam, deliberately not in a loader or
 * kernel build. The retained all-six size/restore session MUST be this owner's
 * actual completed session, not reconstructed historical evidence. FDT/session/
 * sizes/config and output storage are stable, disjoint and serialized by that
 * owner for the entire operation. Existing config callbacks still guard every
 * transaction and authorize every write; no callback may change owner or retry.
 * The provider must reverify actual outbound programming under its lifecycle
 * checks. Comparing its software plan here is not fresh hardware proof.
 *
 * Assign writes only exact planned MEM32 BAR values, then independently reads
 * all six slots back. COMMAND.IO/MEM/BME must remain zero; COMMAND, ROM, reset,
 * MSI and endpoint register space are never written. Restore is a separate,
 * one-shot operation from ASSIGNED only: verify the still-assigned live header,
 * restore every implemented slot, independently verify every original. Success
 * means exact BAR restoration, not DMA quiescence or a functioning device.
 *
 * Any transfer/readback failure terminally quarantines this session. Config
 * engine quarantine rules remain unchanged; even a failed acquisition permits
 * no unlocked config mutation. No cleanup runs after failure: posted writes may
 * leave some slots assigned/restored, and the watchdog recovery remains owned
 * by the caller. No output is published after failure and no retry is admitted.
 * At most 76 config transfers across successful assign+restore; no polling. */
int rpi5_rp1_assignment_write_allowed(const struct rpi5_rp1_assignment *,
    const struct rpi5_pcie_config_request *);
int rpi5_rp1_bars_assign(struct rpi5_rp1_assignment *, struct rpi5_pcie_config *,
    const struct rpi5_pcie_fdt *, const struct rpi5_rp1_bars_probe *,
    const struct rpi5_rp1_bars_size *, const struct rpi5_rp1_assignment_source *,
    struct rpi5_rp1_assignment_observation *);
int rpi5_rp1_bars_restore(struct rpi5_rp1_assignment *,
    struct rpi5_rp1_assignment_observation *);

/* Pure proposed Device-map geometry, usable only while the assignment is live.
 * No Device mapping, COMMAND.MEM enable, device reads, IRQ or DMA authority is
 * granted. A real mapping owner must bind this to its current lease, use Device
 * attributes, and revoke mappings before restoring/reassigning the BARs. Output
 * unchanged on failure. Deliberately does not fake memory_decode_enabled=1 to
 * reuse the existing enabled-resource planner. */
int rpi5_rp1_bars_mapping_candidate(const struct rpi5_rp1_assignment *,
    const struct rpi5_pcie_fdt *, struct rpi5_rp1_mapping_candidate *);
#endif
