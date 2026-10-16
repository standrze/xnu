/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_SERDES_H
#define RPI5_PCIE_SERDES_H

#include "pcie_mdio.h"
#include "pcie_rescal.h"
#include "pcie_reset.h"

enum rpi5_pcie_serdes_state {
    RPI5_PCIE_SERDES_EMPTY, RPI5_PCIE_SERDES_READY,
    RPI5_PCIE_SERDES_BUSY, RPI5_PCIE_SERDES_COMPLETE,
    RPI5_PCIE_SERDES_QUARANTINED
};
enum rpi5_pcie_serdes_result {
    RPI5_PCIE_SERDES_OK = 0, RPI5_PCIE_SERDES_ARGUMENT = -1,
    RPI5_PCIE_SERDES_STATE = -2, RPI5_PCIE_SERDES_IO = -3,
    RPI5_PCIE_SERDES_READBACK = -4, RPI5_PCIE_SERDES_DEPENDENCY = -5,
    RPI5_PCIE_SERDES_MDIO = -6
};
struct rpi5_pcie_serdes {
    struct rpi5_pcie_mdio mdio;
    const struct rpi5_pcie_rescal *calibration;
    const struct rpi5_pcie_reset *bridge_reset;
    enum rpi5_pcie_serdes_state state;
    uint32_t completed_actions; /* direct callbacks plus completed MDIO writes */
    int last_mdio_result;
};
struct rpi5_pcie_serdes_observation {
    uint32_t hard_debug_before, hard_debug_after;
    uint32_t phy_control_before, phy_control_after;
    uint32_t mdio_writes_completed, mdio_poll_reads;
};

/* Pure init, no I/O. Requires completed shared calibration and PCIe2 bridge
 * reset sessions, disjoint stable objects, and zero-initialized output session.
 * Provider retains exclusive bridge/MDIO/shared calibration lifecycle and
 * power/clock/Device accessibility throughout. Software session states are not
 * proof of real hardware ownership or a safe mapping.
 * This BCM2712 fixed 54-MHz path is not a generic PCIe/PHY initializer. */
int rpi5_pcie_serdes_init(struct rpi5_pcie_serdes *, const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_mdio_io *, const struct rpi5_pcie_rescal *,
    const struct rpi5_pcie_reset *);

/* One initial sequence: clear SERDES_IDDQ in BCM2712 HARD_DEBUG (0x4304),
 * order/wait >=100 us/verify, write the fixed eight-command port-0 block-1600
 * 54-MHz profile, wait >=100 us, and set PHY_CTL_15 (0x184c) low byte to 0x12
 * preserving other bits and verifying the target field.
 *
 * This performs NO SSC, PERST, config/BAR, window, bus-master, interrupt or DMA
 * operation. UBUS error handling/timeouts/QoS, RC setup and trained link remain
 * separate requirements. MDIO handshake completion is not retained-register
 * or electrical-quality proof. No boot/MMIO caller exists yet.
 * Failure quarantines both SerDes and embedded MDIO, commits no observation,
 * and performs no rollback, cleanup or retry. Already-issued writes persist.
 * last_mdio_result preserves the underlying error when result is MDIO.
 * A completed/failed session cannot be recycled with init. */
int rpi5_pcie_serdes_configure54(struct rpi5_pcie_serdes *,
    struct rpi5_pcie_serdes_observation *out);

#endif
