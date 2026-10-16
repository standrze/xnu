/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_LINK_H
#define RPI5_PCIE_LINK_H

#include "pcie_ubus.h"
#include "pcie_windows.h"
#include "pcie_rc.h"

/* Exact PCIe2 Gen2/x4 diagnostic profile, with no SSC, ASPM/L1SS or optional
 * Tperst_clk extension. Provider must review the original FDT properties, not
 * infer absent options from fields omitted by the resource decoder.
 * check_lifecycle must keep the RC configuration, windows, SerDes and UBUS
 * sessions exclusively owned, powered, clocked and fault-contained; unused
 * windows must be disabled/safe, endpoint bus mastering and DMA quiesced.
 * released=0 additionally requires asserted PERST#; released=1 must NOT require
 * link down or asserted PERST#. Neither phase permits endpoint/config access.
 * Each callback must terminate independently; finite polling cannot contain a
 * hung access or CPU abort. read16/write16 are real LE halfword transactions,
 * NOT 32-bit RMW of adjacent link-status/W1C fields. No callback may reenter. */
struct rpi5_pcie_link_io {
    int (*check_lifecycle)(void *context, unsigned released);
    int (*read16)(void *context, uint32_t offset, uint16_t *);
    int (*write16)(void *context, uint32_t offset, uint16_t);
    struct rpi5_pcie_rc *rc; /* COMPLETE, same windows/halfword IO/reset owners. */
};
enum rpi5_pcie_link_state {
    RPI5_PCIE_LINK_EMPTY, RPI5_PCIE_LINK_READY, RPI5_PCIE_LINK_BUSY,
    RPI5_PCIE_LINK_COMPLETE, RPI5_PCIE_LINK_QUARANTINED
};
enum rpi5_pcie_link_result {
    RPI5_PCIE_LINK_OK = 0, RPI5_PCIE_LINK_ARGUMENT = -1,
    RPI5_PCIE_LINK_STATE = -2, RPI5_PCIE_LINK_DEPENDENCY = -3,
    RPI5_PCIE_LINK_IO = -4, RPI5_PCIE_LINK_READBACK = -5,
    RPI5_PCIE_LINK_NOT_QUIESCENT = -6, RPI5_PCIE_LINK_CLOCK = -7,
    RPI5_PCIE_LINK_TIMEOUT = -8, RPI5_PCIE_LINK_PROFILE = -9,
    RPI5_PCIE_LINK_LOST = -10
};
struct rpi5_pcie_link {
    struct rpi5_pcie_ubus *ubus;
    struct rpi5_pcie_windows *windows;
    struct rpi5_pcie_link_io io;
    enum rpi5_pcie_link_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_link_observation {
    uint32_t status_before, control_before, control_released;
    uint32_t capability_before, capability_after, debug_before, debug_after;
    uint32_t status_up, status_final, poll_reads, generation, lanes;
    uint16_t control2_before, control2_after, negotiated;
    uint64_t reset_wait_us, poll_elapsed_us;
};

/* Pure one-shot init, zero-initialized disjoint storage. Both COMPLETE
 * prerequisites and io.rc must refer to the SAME mapping, callbacks and owner.
 * Software states and successful init do not establish hardware admission. */
int rpi5_pcie_link_init(struct rpi5_pcie_link *, struct rpi5_pcie_ubus *,
    struct rpi5_pcie_windows *, const struct rpi5_pcie_link_io *);

/* Recheck RC misc/class/endian/x4/ASPM/SerDes profile and asserted PERST#;
 * program Gen2 using 32-bit link capability and 16-bit target-link control;
 * disable CLKREQ/L1SS overrides, release PERST# (bit 2 of 0x4064), verify
 * at least 100 ms settling (<=110 ms allowed), poll <=100 ms/21 reads at
 * >=5-ms intervals, then verify negotiated Gen1/2 x1/2/4 and stable link.
 * At most 121 callbacks on the successful latest-link path; setup/callback
 * and final-verification latency are separate provider bounds, not included
 * in the poll deadline. No wall-clock bound for hung MMIO is established here.
 * Downtrained speed/width are recorded, not claimed as full bandwidth.
 * Link-ready does not mean config/BAR/IRQ/DMA/NIC-ready; those remain separate.
 * Failure leaves output unchanged and quarantines link/windows/UBUS/SerDes/
 * MDIO sessions, without cleanup, retraining, reset, delay or rollback.
 * Already-issued writes and a released PERST# may persist after failure.
 * RC setup is also quarantined. Shared reset/calibration are not shut down. No boot/MMIO caller
 * exists yet; this module is absent from actual BL33/XNU source lists. */
int rpi5_pcie_link_train(struct rpi5_pcie_link *, struct rpi5_pcie_link_observation *);

#endif
