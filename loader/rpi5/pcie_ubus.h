/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_UBUS_H
#define RPI5_PCIE_UBUS_H

#include "pcie_serdes.h"

enum rpi5_pcie_ubus_state {
    RPI5_PCIE_UBUS_EMPTY, RPI5_PCIE_UBUS_READY, RPI5_PCIE_UBUS_BUSY,
    RPI5_PCIE_UBUS_COMPLETE, RPI5_PCIE_UBUS_QUARANTINED
};
enum rpi5_pcie_ubus_result {
    RPI5_PCIE_UBUS_OK = 0, RPI5_PCIE_UBUS_ARGUMENT = -1,
    RPI5_PCIE_UBUS_STATE = -2, RPI5_PCIE_UBUS_DEPENDENCY = -3,
    RPI5_PCIE_UBUS_IO = -4, RPI5_PCIE_UBUS_READBACK = -5
};
struct rpi5_pcie_ubus {
    struct rpi5_pcie_serdes *serdes;
    enum rpi5_pcie_ubus_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_ubus_observation {
    uint32_t ubus_before, ubus_after;
    uint32_t ubus_timeout, config_retry_timeout;
    uint32_t axi_before, axi_after, axi_final;
    uint32_t control_before, control_after;
    uint32_t outstanding_fallback;
};

/* Pure init; one-shot BCM2712 PCIe2 post-SerDes UBUS/AXI defaults. The stable,
 * disjoint SerDes session and its actual Device/clock/reset ownership provider
 * must remain exclusively held. Software COMPLETE states do not establish
 * accessibility, fault containment or actual power/clock ownership.
 * Used sessions cannot be reinitialized. No boot/MMIO caller exists yet. */
int rpi5_pcie_ubus_init(struct rpi5_pcie_ubus *, struct rpi5_pcie_serdes *);

/* Enable error-response suppression, set read-error data to all ones, program
 * reference UBUS/config-retry timeouts, apply AXI QoS fix bits and the Reserved-0
 * timing-bit fallback (15 outstanding requests), and disable VDM QoS reception.
 * Finite <=30 callbacks; no polls. Provider must independently bound callbacks
 * and contain faults. All-ones register reads reject; the intentional all-ones
 * error-data write is not read back or claimed to prove MMIO accessibility.
 * Optional FIFO/VDM maps, RC mode/class/misc setup, windows, PERST/link training,
 * config selection, endpoint BARs, interrupts, bus mastering and DMA remain
 * separate requirements. COMPLETE means only this fixed subset completed.
 * On failure, quarantine this session, SerDes and its MDIO transport; leave
 * output unchanged. Already-issued writes persist, no cleanup/retry/rollback.
 * Shared calibration/reset providers are never reset or shut down here. */
int rpi5_pcie_ubus_configure(struct rpi5_pcie_ubus *,
    struct rpi5_pcie_ubus_observation *out);

#endif
