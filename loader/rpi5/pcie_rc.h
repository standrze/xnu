/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_RC_H
#define RPI5_PCIE_RC_H

#include "pcie_windows.h"
#include "pcie_reset.h"
#include "pcie_rescal.h"

struct rpi5_pcie_rc_io {
    /* Same owner/context as windows.io. Real little-endian halfword accesses,
     * not a word RMW touching the adjacent link-status register. */
    int (*read16)(void *, uint32_t offset, uint16_t *);
    int (*write16)(void *, uint32_t offset, uint16_t);
};
enum rpi5_pcie_rc_state {
    RPI5_PCIE_RC_EMPTY, RPI5_PCIE_RC_READY, RPI5_PCIE_RC_BUSY,
    RPI5_PCIE_RC_COMPLETE, RPI5_PCIE_RC_QUARANTINED
};
enum rpi5_pcie_rc_result {
    RPI5_PCIE_RC_OK = 0, RPI5_PCIE_RC_ARGUMENT = -1,
    RPI5_PCIE_RC_STATE = -2, RPI5_PCIE_RC_DEPENDENCY = -3,
    RPI5_PCIE_RC_IO = -4, RPI5_PCIE_RC_READBACK = -5,
    RPI5_PCIE_RC_NOT_QUIESCENT = -6, RPI5_PCIE_RC_PROFILE = -7,
    RPI5_PCIE_RC_WINDOWS = -8
};
struct rpi5_pcie_rc {
    struct rpi5_pcie_windows *windows;
    const struct rpi5_pcie_reset *bridge_reset;
    const struct rpi5_pcie_rescal *calibration;
    struct rpi5_pcie_rc_io io;
    enum rpi5_pcie_rc_state state;
    uint32_t completed_callbacks; /* Direct RC callbacks, excludes window core. */
    int last_windows_result;
};
struct rpi5_pcie_rc_observation {
    uint32_t misc_before, misc_after, capability;
    uint32_t class_before, class_after, endian_before, endian_after;
    uint16_t link_control_before, link_control_after;
    uint32_t final_status, final_control, completed_callbacks, window_callbacks;
};

/* Pure one-shot init for stable, disjoint, zero-initialized storage. Requires
 * an unconsumed READY window session and COMPLETE shared calibration/bridge
 * reset. Those states do NOT prove physical ownership or accessibility.
 * windows.check_quiescent must retain accessible Device/power/clock/shared
 * ownership, contain/bound all callbacks, verify unused windows disabled/safe,
 * keep PERST# asserted, interrupt delivery masked and endpoint bus mastering/
 * DMA quiesced. Provider must
 * establish IDDQ release/settling before this operation, and inspect original
 * FDT options for the fixed x4/no-ASPM/clock-PM diagnostic policy. No inference
 * of absent options from the reduced decoder is permitted. */
int rpi5_pcie_rc_init(struct rpi5_pcie_rc *, struct rpi5_pcie_windows *,
    const struct rpi5_pcie_reset *, const struct rpi5_pcie_rescal *,
    const struct rpi5_pcie_rc_io *);

/* Set BCM2712 burst/SCB/UR/RCB fields, call the ACTUAL window programmer once,
 * set bridge class/little-endian inbound mode and disable root ASPM/clock PM
 * with real 16-bit access. Require native x4, never invent a width override or
 * SCB RAM-size value from the board's 8 GB. Preserve unrelated config bits;
 * ordered writes, immediate and independent final readbacks, quiescent guards.
 * At most 34 direct +112 window callbacks. No polls, PERST release, config
 * selector/endpoint/BAR, IRQ/MSI, bus mastering, DMA or kernel attachment.
 * Finite callback count does not contain hung MMIO/abort. On any failure,
 * output unchanged, RC/windows quarantined, no cleanup/retry/reset/rollback.
 * Shared reset/calibration are not released/shut down. Existing writes persist.
 * Absent from actual boot builds pending the hardware provider/recovery gate. */
int rpi5_pcie_rc_configure(struct rpi5_pcie_rc *, struct rpi5_pcie_rc_observation *);

#endif
