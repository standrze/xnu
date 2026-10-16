/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_mdio.h"

#define BRIDGE_BASE UINT64_C(0x1000120000)
#define BRIDGE_BYTES UINT64_C(0x9310)
#define ADDRESS UINT32_C(0x1100)
#define WRITE_DATA UINT32_C(0x1104)
#define READ_DATA UINT32_C(0x1108)
#define READ_COMMAND UINT32_C(0x00100000)
#define DONE UINT32_C(0x80000000)
#define PAYLOAD UINT32_C(0x7fffffff)
#define POLL_US UINT32_C(10)
#define TIMEOUT_US UINT64_C(100)

int rpi5_pcie_mdio_init(struct rpi5_pcie_mdio *session,
    const struct rpi5_pcie_fdt *fdt, const struct rpi5_pcie_mdio_io *io)
{
    if (!session || !fdt || !io || !io->read32 || !io->write32 || !io->order ||
        !io->now_us || !io->delay_us || fdt->bridge_regs.start != BRIDGE_BASE ||
        fdt->bridge_regs.end != BRIDGE_BASE + BRIDGE_BYTES ||
        io->physical_base != BRIDGE_BASE || io->mapped_bytes != BRIDGE_BYTES)
        return RPI5_PCIE_MDIO_ARGUMENT;
    if (session->state != RPI5_PCIE_MDIO_EMPTY) return RPI5_PCIE_MDIO_STATE;
    session->io.context = io->context;
    session->io.physical_base = io->physical_base;
    session->io.mapped_bytes = io->mapped_bytes;
    session->io.read32 = io->read32;
    session->io.write32 = io->write32;
    session->io.order = io->order;
    session->io.now_us = io->now_us;
    session->io.delay_us = io->delay_us;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_MDIO_READY;
    return RPI5_PCIE_MDIO_OK;
}

static int quarantine(struct rpi5_pcie_mdio *session, int rc)
{
    session->state = RPI5_PCIE_MDIO_QUARANTINED;
    return rc;
}

static int transaction(struct rpi5_pcie_mdio *session, uint8_t reg,
    int reading, uint16_t value, struct rpi5_pcie_mdio_observation *out)
{
    if (!session || !out || reg > 31) return RPI5_PCIE_MDIO_ARGUMENT;
    if (session->state != RPI5_PCIE_MDIO_READY) return RPI5_PCIE_MDIO_STATE;
    session->state = RPI5_PCIE_MDIO_BUSY;
    session->completed_callbacks = 0;
    const struct rpi5_pcie_mdio_io *io = &session->io;
    struct rpi5_pcie_mdio_observation result;
    uint64_t start, last, now;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_MDIO_IO); \
    session->completed_callbacks++; \
} while (0)
    STEP(io->read32(io->context, WRITE_DATA, &result.idle_write_data));
    if (result.idle_write_data == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_MDIO_READBACK);
    if (result.idle_write_data & DONE)
        return quarantine(session, RPI5_PCIE_MDIO_ALREADY_BUSY);
    result.command = (reading ? READ_COMMAND : 0) | reg;
    STEP(io->write32(io->context, ADDRESS, result.command));
    STEP(io->order(io->context));
    STEP(io->read32(io->context, ADDRESS, &result.address_readback));
    if (result.address_readback == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_MDIO_READBACK);
    if (!reading) {
        STEP(io->write32(io->context, WRITE_DATA, DONE | value));
        STEP(io->order(io->context));
    }
    STEP(io->now_us(io->context, &start));
    last = start;
    result.poll_reads = 0;
    for (;;) {
        STEP(io->read32(io->context, reading ? READ_DATA : WRITE_DATA, &result.final_data));
        result.poll_reads++;
        if (result.final_data == UINT32_MAX)
            return quarantine(session, RPI5_PCIE_MDIO_READBACK);
        STEP(io->now_us(io->context, &now));
        if (now < last) return quarantine(session, RPI5_PCIE_MDIO_CLOCK);
        result.poll_elapsed_us = now - start;
        if (result.poll_elapsed_us > TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_MDIO_TIMEOUT);
        if (!!(result.final_data & DONE) == reading) break;
        if (result.poll_reads == 11 || result.poll_elapsed_us == TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_MDIO_TIMEOUT);
        last = now;
        STEP(io->delay_us(io->context, POLL_US));
        STEP(io->now_us(io->context, &now));
        if (now < last) return quarantine(session, RPI5_PCIE_MDIO_CLOCK);
        if (now - start > TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_MDIO_TIMEOUT);
        last = now;
    }
#undef STEP
    result.payload = result.final_data & PAYLOAD;
    out->command = result.command;
    out->address_readback = result.address_readback;
    out->idle_write_data = result.idle_write_data;
    out->final_data = result.final_data;
    out->payload = result.payload;
    out->poll_reads = result.poll_reads;
    out->poll_elapsed_us = result.poll_elapsed_us;
    session->state = RPI5_PCIE_MDIO_READY;
    return RPI5_PCIE_MDIO_OK;
}

int rpi5_pcie_mdio_read(struct rpi5_pcie_mdio *session, uint8_t reg,
    struct rpi5_pcie_mdio_observation *out)
{
    return transaction(session, reg, 1, 0, out);
}

int rpi5_pcie_mdio_write(struct rpi5_pcie_mdio *session, uint8_t reg, uint16_t value,
    struct rpi5_pcie_mdio_observation *out)
{
    return transaction(session, reg, 0, value, out);
}
