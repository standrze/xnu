/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_CLOCK_H
#define RPI5_PCIE_CLOCK_H
#include "pcie_qos.h"
#include "pcie_link.h"

enum rpi5_pcie_clock_state {
    RPI5_PCIE_CLOCK_EMPTY, RPI5_PCIE_CLOCK_READY, RPI5_PCIE_CLOCK_BUSY,
    RPI5_PCIE_CLOCK_PREPARED, RPI5_PCIE_CLOCK_COMPLETE, RPI5_PCIE_CLOCK_QUARANTINED
};
enum rpi5_pcie_clock_result {
    RPI5_PCIE_CLOCK_OK = 0, RPI5_PCIE_CLOCK_ARGUMENT = -1,
    RPI5_PCIE_CLOCK_STATE = -2, RPI5_PCIE_CLOCK_DEPENDENCY = -3,
    RPI5_PCIE_CLOCK_IO = -4, RPI5_PCIE_CLOCK_READBACK = -5,
    RPI5_PCIE_CLOCK_PROFILE = -6, RPI5_PCIE_CLOCK_LIFECYCLE = -7
};
struct rpi5_pcie_clock {
    struct rpi5_pcie_qos *qos;
    struct rpi5_pcie_link *link;
    struct rpi5_pcie_profile profile;
    enum rpi5_pcie_clock_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_clock_pre_observation {
    uint32_t capability_before, capability_after, writes, completed_callbacks;
};
struct rpi5_pcie_clock_post_observation {
    uint32_t declared_mode, effective_mode;
    uint32_t root_before, root_after, debug_before, debug_after;
    uint32_t final_status, writes, completed_callbacks;
};
/* Pure one-shot init from the SAME actually completed QoS/UBUS/SerDes/reset/
 * calibration chain and validated full-FDT profile. Stable/disjoint sessions
 * must not be mutated or reentered by callbacks. State is not physical proof.
 * The caller still needs independently admitted Device accessibility, inherited
 * power/clocks/shared-domain ownership, IRQ/endpoint/DMA quiescence, bounded
 * fault-contained callbacks and autonomous recovery, as for the prior stages. */
int rpi5_pcie_clock_init(struct rpi5_pcie_clock *, struct rpi5_pcie_qos *);
/* Before RC/windows/link: honor aspm-no-l0s by clearing capability bit 10,
 * preserving all other fields. If absent, do not write or enable L0s. Require
 * native x4, RC role, link down, asserted PERST, no L23/IDDQ/forced reset and
 * existing AXI fixes. No CLKREQ, PERST, root-ASPM/clock-PM or window writes.
 * Immediate and independent final verification; at most 61 callbacks.
 * Successful PREPARED is not link or electrical clock readiness. */
int rpi5_pcie_clock_prepare(struct rpi5_pcie_clock *,
    struct rpi5_pcie_clock_pre_observation *);
/* Only AFTER the actual completed link using the SAME owner, reset, mapping,
 * windows and halfword callbacks. New, unbound bad arguments/dependencies are
 * rejected without callbacks/mutation; a bound runtime failure quarantines.
 * Follow the controller's modes: absent resolves explicitly to default; safe
 * drives refclk and removes L1SS advertisement; no-l1ss uses CLKREQ debug and
 * removes L1SS advertisement; default sets controller L1SS support without
 * changing inherited root advertisement. BCM2712 has no RGR1 timeout timer:
 * do NOT write 0x9208 or confuse it with the UBUS timeout at 0x40a8.
 * Root ASPM/clock-PM must remain disabled; this does not enable endpoint or
 * root power management, prove CLKREQ wiring/timing or permit enumeration.
 * True LE16 read of link control, never adjacent W1C/status RMW. Guard owner/
 * dependencies around every callback; check actual active link before each
 * target and final publication. <=160 callbacks, no waits/polls/retraining.
 * On operational failure both phases leave output unchanged and quarantine
 * clock/QoS/UBUS/SerDes/MDIO and bound link/windows/RC. No cleanup, retry, shared
 * reset, rollback or lease release; already-issued writes may persist. Finite
 * counts do not contain hung/aborting MMIO. Not a boot/hardware admission. */
int rpi5_pcie_clock_finish(struct rpi5_pcie_clock *, struct rpi5_pcie_link *,
    struct rpi5_pcie_clock_post_observation *);
#endif
