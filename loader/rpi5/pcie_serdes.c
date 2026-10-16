/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_serdes.h"

#define HARD_DEBUG UINT32_C(0x4304)
#define IDDQ UINT32_C(0x08000000)
#define PHY_CONTROL UINT32_C(0x184c)

int rpi5_pcie_serdes_init(struct rpi5_pcie_serdes *session,
    const struct rpi5_pcie_fdt *fdt, const struct rpi5_pcie_mdio_io *io,
    const struct rpi5_pcie_rescal *calibration, const struct rpi5_pcie_reset *reset)
{
    if (!session || !fdt || !io || !calibration || !reset)
        return RPI5_PCIE_SERDES_ARGUMENT;
    if (session->state != RPI5_PCIE_SERDES_EMPTY || session->mdio.state != RPI5_PCIE_MDIO_EMPTY)
        return RPI5_PCIE_SERDES_STATE;
    if (calibration->state != RPI5_PCIE_RESCAL_COMPLETE || reset->state != RPI5_PCIE_RESET_COMPLETE)
        return RPI5_PCIE_SERDES_DEPENDENCY;
    if (rpi5_pcie_mdio_init(&session->mdio, fdt, io)) return RPI5_PCIE_SERDES_ARGUMENT;
    session->calibration = calibration;
    session->bridge_reset = reset;
    session->completed_actions = 0;
    session->last_mdio_result = RPI5_PCIE_MDIO_OK;
    session->state = RPI5_PCIE_SERDES_READY;
    return RPI5_PCIE_SERDES_OK;
}

static int quarantine(struct rpi5_pcie_serdes *session, int rc)
{
    session->state = RPI5_PCIE_SERDES_QUARANTINED;
    session->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
    return rc;
}

int rpi5_pcie_serdes_configure54(struct rpi5_pcie_serdes *session,
    struct rpi5_pcie_serdes_observation *out)
{
    if (!session || !out) return RPI5_PCIE_SERDES_ARGUMENT;
    if (session->state != RPI5_PCIE_SERDES_READY) return RPI5_PCIE_SERDES_STATE;
    session->state = RPI5_PCIE_SERDES_BUSY;
    if (!session->calibration || !session->bridge_reset ||
        session->calibration->state != RPI5_PCIE_RESCAL_COMPLETE ||
        session->bridge_reset->state != RPI5_PCIE_RESET_COMPLETE ||
        session->mdio.state != RPI5_PCIE_MDIO_READY)
        return quarantine(session, RPI5_PCIE_SERDES_DEPENDENCY);
    const struct rpi5_pcie_mdio_io *io = &session->mdio.io;
    struct rpi5_pcie_serdes_observation result;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_SERDES_IO); \
    session->completed_actions++; \
} while (0)
    STEP(io->read32(io->context, HARD_DEBUG, &result.hard_debug_before));
    if (result.hard_debug_before == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_SERDES_READBACK);
    STEP(io->write32(io->context, HARD_DEBUG, result.hard_debug_before & ~IDDQ));
    STEP(io->order(io->context));
    STEP(io->delay_us(io->context, 100));
    STEP(io->read32(io->context, HARD_DEBUG, &result.hard_debug_after));
    if (result.hard_debug_after == UINT32_MAX || (result.hard_debug_after & IDDQ))
        return quarantine(session, RPI5_PCIE_SERDES_READBACK);

    /* Fixed register/value facts from the Raspberry Pi BCM2712 controller
     * reference, not a generic caller-supplied PHY script or SSC sequence. */
    static const uint8_t regs[8] = {0x1f, 0x16, 0x17, 0x18, 0x19, 0x1b, 0x1c, 0x1e};
    static const uint16_t values[8] = {0x1600, 0x50b9, 0xbda1, 0x0094, 0x97b4, 0x5030, 0x5030, 0x0007};
    result.mdio_writes_completed = result.mdio_poll_reads = 0;
    for (unsigned i = 0; i < 8; i++) {
        struct rpi5_pcie_mdio_observation observed;
        int rc = rpi5_pcie_mdio_write(&session->mdio, regs[i], values[i], &observed);
        session->last_mdio_result = rc;
        if (rc) return quarantine(session, RPI5_PCIE_SERDES_MDIO);
        session->completed_actions++;
        result.mdio_writes_completed++;
        result.mdio_poll_reads += observed.poll_reads;
    }
    STEP(io->delay_us(io->context, 100));
    STEP(io->read32(io->context, PHY_CONTROL, &result.phy_control_before));
    if (result.phy_control_before == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_SERDES_READBACK);
    STEP(io->write32(io->context, PHY_CONTROL, (result.phy_control_before & ~UINT32_C(0xff)) | 0x12));
    STEP(io->order(io->context));
    STEP(io->read32(io->context, PHY_CONTROL, &result.phy_control_after));
    if (result.phy_control_after == UINT32_MAX || (result.phy_control_after & 0xff) != 0x12)
        return quarantine(session, RPI5_PCIE_SERDES_READBACK);
#undef STEP
    out->hard_debug_before = result.hard_debug_before;
    out->hard_debug_after = result.hard_debug_after;
    out->phy_control_before = result.phy_control_before;
    out->phy_control_after = result.phy_control_after;
    out->mdio_writes_completed = result.mdio_writes_completed;
    out->mdio_poll_reads = result.mdio_poll_reads;
    session->state = RPI5_PCIE_SERDES_COMPLETE;
    return RPI5_PCIE_SERDES_OK;
}
