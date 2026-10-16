/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_BAR1_PROBE_H
#define RPI5_RP1_BAR1_PROBE_H
#include "rp1_config_snapshot.h"

enum rpi5_rp1_bar1_state {
    RPI5_RP1_BAR1_EMPTY, RPI5_RP1_BAR1_CHECKING, RPI5_RP1_BAR1_PROBING,
    RPI5_RP1_BAR1_RESTORING, RPI5_RP1_BAR1_VERIFYING,
    RPI5_RP1_BAR1_COMPLETE, RPI5_RP1_BAR1_FAILED
};
struct rpi5_rp1_bar1_probe {
    enum rpi5_rp1_bar1_state state;
    uint32_t original_bar1, transactions, writes_started;
};
struct rpi5_rp1_bar1_size {
    uint32_t original_bar1, mask, size, final_command, transactions;
};

/* Independent narrow authorization predicate for the real owner's callback.
 * It does not establish ownership, accessibility, DMA containment or recovery.
 * Only fixed RP1 BAR1 dword writes in the two explicit phases can pass. */
int rpi5_rp1_bar1_write_allowed(const struct rpi5_rp1_bar1_probe *,
    const struct rpi5_pcie_config_request *);

/* One-shot size probe and exact BAR1 restoration via the actual serialized
 * config engine. Requires the retained same-boot RP1 snapshot, I/O+MEM+BME
 * already disabled and independently checked controller lifecycle. Neither
 * command bits nor BAR assignment/enable are changed. Size is observed from
 * actual mask readback, never inferred from FDT/address zero. The provider must
 * allow only write_allowed requests and independently keep inbound RAM/MSI
 * decode disabled; this function cannot prove hardware containment.
 * No retry/poll/cleanup on failure: BAR may remain in sizing state. Output
 * unchanged, local session latched FAILED, owner must terminally quarantine
 * and use its independently proven watchdog. COMPLETE is size/restoration
 * evidence only, NOT assignment, Device mapping, BAR access or DMA authority.
 * Zeroed disjoint session/output and stable snapshot required, single owner. */
int rpi5_rp1_bar1_probe(struct rpi5_rp1_bar1_probe *, struct rpi5_pcie_config *,
    const struct rpi5_rp1_config_snapshot *, struct rpi5_rp1_bar1_size *);
#endif
