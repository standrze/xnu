/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_rescal.h"

#define RESCAL_BASE UINT64_C(0x1000119500)
#define RESCAL_BYTES UINT64_C(0x10)
#define START_BIT UINT32_C(1)
#define STATUS_BIT UINT32_C(1)
#define POLL_US UINT32_C(100)
#define TIMEOUT_US UINT64_C(1000)
#define MAX_READS UINT32_C(11)

int rpi5_pcie_rescal_init(struct rpi5_pcie_rescal *session,
    const struct rpi5_pcie_fdt *fdt, const struct rpi5_pcie_rescal_io *io)
{
    if (!session || !fdt || !io || !io->claim_shared || !io->read_start ||
        !io->write_start || !io->read_status || !io->order || !io->now_us ||
        !io->delay_us || fdt->rescal_regs.start != RESCAL_BASE ||
        fdt->rescal_regs.end != RESCAL_BASE + RESCAL_BYTES ||
        io->physical_base != RESCAL_BASE || io->mapped_bytes != RESCAL_BYTES)
        return RPI5_PCIE_RESCAL_ARGUMENT;
    if (session->state != RPI5_PCIE_RESCAL_EMPTY)
        return RPI5_PCIE_RESCAL_STATE;
    session->io.context = io->context;
    session->io.physical_base = io->physical_base;
    session->io.mapped_bytes = io->mapped_bytes;
    session->io.claim_shared = io->claim_shared;
    session->io.read_start = io->read_start;
    session->io.write_start = io->write_start;
    session->io.read_status = io->read_status;
    session->io.order = io->order;
    session->io.now_us = io->now_us;
    session->io.delay_us = io->delay_us;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_RESCAL_READY;
    return RPI5_PCIE_RESCAL_OK;
}

static int quarantine(struct rpi5_pcie_rescal *session, int result)
{
    session->state = RPI5_PCIE_RESCAL_QUARANTINED;
    return result;
}

int rpi5_pcie_rescal_calibrate(struct rpi5_pcie_rescal *session,
    struct rpi5_pcie_rescal_observation *out)
{
    if (!session || !out) return RPI5_PCIE_RESCAL_ARGUMENT;
    if (session->state != RPI5_PCIE_RESCAL_READY) return RPI5_PCIE_RESCAL_STATE;
    session->state = RPI5_PCIE_RESCAL_BUSY;
    const struct rpi5_pcie_rescal_io *io = &session->io;
    struct rpi5_pcie_rescal_observation result;
    uint64_t start, last, now;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_RESCAL_IO); \
    session->completed_callbacks++; \
} while (0)
    STEP(io->claim_shared(io->context));
    STEP(io->read_start(io->context, &result.initial_start));
    if (result.initial_start == UINT32_MAX)
        return quarantine(session, RPI5_PCIE_RESCAL_READBACK);
    if (result.initial_start & START_BIT)
        return quarantine(session, RPI5_PCIE_RESCAL_ALREADY_STARTED);
    STEP(io->write_start(io->context, result.initial_start | START_BIT));
    STEP(io->order(io->context));
    STEP(io->read_start(io->context, &result.asserted_start));
    if (result.asserted_start == UINT32_MAX || !(result.asserted_start & START_BIT))
        return quarantine(session, RPI5_PCIE_RESCAL_READBACK);
    STEP(io->now_us(io->context, &start));
    last = start;
    result.status_reads = 0;
    for (;;) {
        STEP(io->read_status(io->context, &result.completion_status));
        result.status_reads++;
        if (result.completion_status == UINT32_MAX)
            return quarantine(session, RPI5_PCIE_RESCAL_READBACK);
        STEP(io->now_us(io->context, &now));
        if (now < last) return quarantine(session, RPI5_PCIE_RESCAL_CLOCK);
        result.poll_elapsed_us = now - start;
        if (result.poll_elapsed_us > TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_RESCAL_TIMEOUT);
        if (result.completion_status & STATUS_BIT) break;
        if (result.status_reads == MAX_READS || result.poll_elapsed_us == TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_RESCAL_TIMEOUT);
        last = now;
        STEP(io->delay_us(io->context, POLL_US));
        STEP(io->now_us(io->context, &now));
        if (now < last) return quarantine(session, RPI5_PCIE_RESCAL_CLOCK);
        if (now - start > TIMEOUT_US)
            return quarantine(session, RPI5_PCIE_RESCAL_TIMEOUT);
        last = now;
    }
    STEP(io->read_start(io->context, &result.before_clear));
    if (result.before_clear == UINT32_MAX || !(result.before_clear & START_BIT))
        return quarantine(session, RPI5_PCIE_RESCAL_READBACK);
    STEP(io->write_start(io->context, result.before_clear & ~START_BIT));
    STEP(io->order(io->context));
    STEP(io->read_start(io->context, &result.cleared_start));
    if (result.cleared_start == UINT32_MAX || (result.cleared_start & START_BIT))
        return quarantine(session, RPI5_PCIE_RESCAL_READBACK);
#undef STEP
    out->initial_start = result.initial_start;
    out->asserted_start = result.asserted_start;
    out->completion_status = result.completion_status;
    out->before_clear = result.before_clear;
    out->cleared_start = result.cleared_start;
    out->status_reads = result.status_reads;
    out->poll_elapsed_us = result.poll_elapsed_us;
    session->state = RPI5_PCIE_RESCAL_COMPLETE;
    return RPI5_PCIE_RESCAL_OK;
}
