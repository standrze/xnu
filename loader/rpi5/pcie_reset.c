/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_reset.h"

#define RESET_BASE UINT64_C(0x1001504318)
#define RESET_BYTES UINT64_C(0x30)
#define BRIDGE_BIT UINT32_C(0x1000)
#define SETTLE_US UINT32_C(100)

int rpi5_pcie_reset_init(struct rpi5_pcie_reset *session,
    const struct rpi5_pcie_fdt *fdt, const struct rpi5_pcie_reset_io *io)
{
    if (!session || !fdt || !io || !io->status || !io->assert_bridge ||
        !io->deassert_bridge || !io->order || !io->delay_us ||
        fdt->bridge_reset_id != 44 ||
        fdt->bridge_reset_regs.start != RESET_BASE ||
        fdt->bridge_reset_regs.end != RESET_BASE + RESET_BYTES ||
        io->physical_base != RESET_BASE || io->mapped_bytes != RESET_BYTES)
        return RPI5_PCIE_RESET_ARGUMENT;
    if (session->state != RPI5_PCIE_RESET_EMPTY)
        return RPI5_PCIE_RESET_STATE;
    session->io.context = io->context;
    session->io.physical_base = io->physical_base;
    session->io.mapped_bytes = io->mapped_bytes;
    session->io.status = io->status;
    session->io.assert_bridge = io->assert_bridge;
    session->io.deassert_bridge = io->deassert_bridge;
    session->io.order = io->order;
    session->io.delay_us = io->delay_us;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_RESET_READY;
    return RPI5_PCIE_RESET_OK;
}

static int quarantine(struct rpi5_pcie_reset *session, int result)
{
    session->state = RPI5_PCIE_RESET_QUARANTINED;
    return result;
}

int rpi5_pcie_reset_pulse(struct rpi5_pcie_reset *session,
    struct rpi5_pcie_reset_observation *out)
{
    if (!session || !out) return RPI5_PCIE_RESET_ARGUMENT;
    if (session->state != RPI5_PCIE_RESET_READY)
        return RPI5_PCIE_RESET_STATE;
    /* Own the operation before the first callback, including read-only ones. */
    session->state = RPI5_PCIE_RESET_BUSY;
    const struct rpi5_pcie_reset_io *io = &session->io;
    struct rpi5_pcie_reset_observation result;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_RESET_IO); \
    session->completed_callbacks++; \
} while (0)
    STEP(io->status(io->context, &result.before));
    if (result.before == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_RESET_READBACK);
    STEP(io->assert_bridge(io->context));
    STEP(io->order(io->context));
    STEP(io->delay_us(io->context, SETTLE_US));
    STEP(io->status(io->context, &result.asserted));
    if (result.asserted == UINT32_MAX || !(result.asserted & BRIDGE_BIT))
        return quarantine(session, RPI5_PCIE_RESET_READBACK);
    STEP(io->deassert_bridge(io->context));
    STEP(io->order(io->context));
    STEP(io->delay_us(io->context, SETTLE_US));
    STEP(io->status(io->context, &result.released));
    if (result.released == UINT32_MAX || (result.released & BRIDGE_BIT))
        return quarantine(session, RPI5_PCIE_RESET_READBACK);
#undef STEP
    out->before = result.before;
    out->asserted = result.asserted;
    out->released = result.released;
    session->state = RPI5_PCIE_RESET_COMPLETE;
    return RPI5_PCIE_RESET_OK;
}
