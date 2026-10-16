/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_link.h"

#define STATUS UINT32_C(0x4068)
#define CONTROL UINT32_C(0x4064)
#define PERST_RELEASE UINT32_C(4)
#define DEBUG UINT32_C(0x4304)
#define CLKREQ UINT32_C(0x00310002)
#define IDDQ_FORCE_RESET UINT32_C(0x08000008)
#define CAPABILITY UINT32_C(0x04dc)
#define CONTROL2 UINT32_C(0x00dc)
#define LINK_CONTROL UINT32_C(0x00bc)
#define LINK_STATUS UINT32_C(0x00be)
#define RESET_WAIT UINT32_C(100000)
#define RESET_LIMIT UINT64_C(110000)
#define POLL_WAIT UINT32_C(5000)
#define POLL_LIMIT UINT64_C(100000)

static int dependencies(const struct rpi5_pcie_ubus *u,
    const struct rpi5_pcie_windows *w, const struct rpi5_pcie_link_io *link_io)
{
    if (!u || !w || u->state != RPI5_PCIE_UBUS_COMPLETE ||
        w->state != RPI5_PCIE_WINDOWS_COMPLETE || !u->serdes || !link_io->rc ||
        link_io->rc->state != RPI5_PCIE_RC_COMPLETE || link_io->rc->windows != w ||
        link_io->rc->io.read16 != link_io->read16 ||
        link_io->rc->io.write16 != link_io->write16)
        return 0;
    const struct rpi5_pcie_serdes *s = u->serdes;
    const struct rpi5_pcie_mdio_io *io = &s->mdio.io;
    return s->state == RPI5_PCIE_SERDES_COMPLETE &&
        s->mdio.state == RPI5_PCIE_MDIO_READY && s->bridge_reset && s->calibration &&
        s->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE &&
        s->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        link_io->rc->bridge_reset == s->bridge_reset &&
        link_io->rc->calibration == s->calibration &&
        io->physical_base == UINT64_C(0x1000120000) && io->mapped_bytes == 0x9310 &&
        io->read32 && io->write32 && io->order && io->now_us && io->delay_us &&
        w->io.physical_base == io->physical_base && w->io.mapped_bytes == io->mapped_bytes &&
        w->io.context == io->context && w->io.read32 == io->read32 &&
        w->io.write32 == io->write32 && w->io.order == io->order;
}

int rpi5_pcie_link_init(struct rpi5_pcie_link *session, struct rpi5_pcie_ubus *ubus,
    struct rpi5_pcie_windows *windows, const struct rpi5_pcie_link_io *io)
{
    if (!session || !io || !io->check_lifecycle || !io->read16 || !io->write16)
        return RPI5_PCIE_LINK_ARGUMENT;
    if (session->state != RPI5_PCIE_LINK_EMPTY) return RPI5_PCIE_LINK_STATE;
    if (!dependencies(ubus, windows, io)) return RPI5_PCIE_LINK_DEPENDENCY;
    session->ubus = ubus;
    session->windows = windows;
    session->io.check_lifecycle = io->check_lifecycle;
    session->io.read16 = io->read16;
    session->io.write16 = io->write16;
    session->io.rc = io->rc;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_LINK_READY;
    return RPI5_PCIE_LINK_OK;
}

static int quarantine(struct rpi5_pcie_link *session, int rc)
{
    session->state = RPI5_PCIE_LINK_QUARANTINED;
    session->windows->state = RPI5_PCIE_WINDOWS_QUARANTINED;
    if (session->io.rc) session->io.rc->state = RPI5_PCIE_RC_QUARANTINED;
    session->ubus->state = RPI5_PCIE_UBUS_QUARANTINED;
    session->ubus->serdes->state = RPI5_PCIE_SERDES_QUARANTINED;
    session->ubus->serdes->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
    return rc;
}

int rpi5_pcie_link_train(struct rpi5_pcie_link *session,
    struct rpi5_pcie_link_observation *out)
{
    if (!session || !out) return RPI5_PCIE_LINK_ARGUMENT;
    if (session->state != RPI5_PCIE_LINK_READY) return RPI5_PCIE_LINK_STATE;
    session->state = RPI5_PCIE_LINK_BUSY;
    if (!dependencies(session->ubus, session->windows, &session->io))
        return quarantine(session, RPI5_PCIE_LINK_DEPENDENCY);
    const struct rpi5_pcie_mdio_io *io = &session->ubus->serdes->mdio.io;
    struct rpi5_pcie_link_observation result;
    uint32_t value, control;
    uint16_t half;
    uint64_t start, last, now;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_LINK_IO); \
    session->completed_callbacks++; \
} while (0)
#define READ(reg, field) do { \
    STEP(io->read32(io->context, (reg), &(field))); \
    if ((field) == UINT32_MAX) return quarantine(session, RPI5_PCIE_LINK_READBACK); \
} while (0)
#define READ16(reg, field) do { \
    STEP(session->io.read16(io->context, (reg), &(field))); \
    if ((field) == UINT16_MAX) return quarantine(session, RPI5_PCIE_LINK_READBACK); \
} while (0)
#define WRITE(reg, field) do { \
    STEP(io->write32(io->context, (reg), (field))); \
    STEP(io->order(io->context)); \
} while (0)
    STEP(session->io.check_lifecycle(io->context, 0));
    READ(STATUS, result.status_before);
    if ((result.status_before & 0xf0) != 0x80)
        return quarantine(session, RPI5_PCIE_LINK_NOT_QUIESCENT);
    READ(CONTROL, result.control_before);
    if (result.control_before & (PERST_RELEASE | 1))
        return quarantine(session, RPI5_PCIE_LINK_NOT_QUIESCENT);
    READ(0x4008, value);
    if ((value & 0x303480) != 0x203480) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ(0x043c, value);
    if ((value & 0xffffff) != 0x060400) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ(0x0188, value);
    if (value & 0xc) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ(0x184c, value);
    if ((value & 0xff) != 0x12) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ16(LINK_CONTROL, half);
    if (half & 0x103) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ(CAPABILITY, result.capability_before);
    if ((result.capability_before & 0x1f0) != 0x40)
        return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ16(CONTROL2, result.control2_before);
    WRITE(CAPABILITY, (result.capability_before & ~UINT32_C(0xf)) | 2);
    READ(CAPABILITY, result.capability_after);
    if (result.capability_after != ((result.capability_before & ~UINT32_C(0xf)) | 2))
        return quarantine(session, RPI5_PCIE_LINK_READBACK);
    STEP(session->io.write16(io->context, CONTROL2, (result.control2_before & ~0xfu) | 2));
    STEP(io->order(io->context));
    READ16(CONTROL2, result.control2_after);
    if (result.control2_after != ((result.control2_before & ~0xfu) | 2))
        return quarantine(session, RPI5_PCIE_LINK_READBACK);
    READ(DEBUG, result.debug_before);
    if (result.debug_before & IDDQ_FORCE_RESET) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    WRITE(DEBUG, result.debug_before & ~CLKREQ);
    READ(DEBUG, result.debug_after);
    if (result.debug_after != (result.debug_before & ~CLKREQ))
        return quarantine(session, RPI5_PCIE_LINK_READBACK);
    STEP(session->io.check_lifecycle(io->context, 0));
    READ(STATUS, value);
    if ((value & 0xf0) != 0x80) return quarantine(session, RPI5_PCIE_LINK_NOT_QUIESCENT);
    READ(CONTROL, control);
    if (control != result.control_before) return quarantine(session, RPI5_PCIE_LINK_NOT_QUIESCENT);
    WRITE(CONTROL, control | PERST_RELEASE);
    READ(CONTROL, result.control_released);
    if (result.control_released != (control | PERST_RELEASE))
        return quarantine(session, RPI5_PCIE_LINK_READBACK);
    /* Start after posted-write completion, so the measured lower bound cannot
     * include time spent before PERST# actually became deasserted. */
    STEP(io->now_us(io->context, &start));
    STEP(io->delay_us(io->context, RESET_WAIT));
    STEP(io->now_us(io->context, &now));
    if (now < start || now - start < RESET_WAIT) return quarantine(session, RPI5_PCIE_LINK_CLOCK);
    result.reset_wait_us = now - start;
    if (result.reset_wait_us > RESET_LIMIT) return quarantine(session, RPI5_PCIE_LINK_TIMEOUT);
    STEP(session->io.check_lifecycle(io->context, 1));
    STEP(io->now_us(io->context, &start));
    if (start < now) return quarantine(session, RPI5_PCIE_LINK_CLOCK);
    last = start;
    result.poll_reads = 0;
    for (;;) {
        READ(STATUS, result.status_up);
        result.poll_reads++;
        STEP(io->now_us(io->context, &now));
        if (now < last) return quarantine(session, RPI5_PCIE_LINK_CLOCK);
        result.poll_elapsed_us = now - start;
        if (result.poll_elapsed_us > POLL_LIMIT) return quarantine(session, RPI5_PCIE_LINK_TIMEOUT);
        if ((result.status_up & 0xc0) != 0x80) return quarantine(session, RPI5_PCIE_LINK_LOST);
        if ((result.status_up & 0x30) == 0x30) break;
        if (result.poll_reads == 21 || result.poll_elapsed_us == POLL_LIMIT)
            return quarantine(session, RPI5_PCIE_LINK_TIMEOUT);
        last = now;
        STEP(io->delay_us(io->context, POLL_WAIT));
        STEP(io->now_us(io->context, &now));
        if (now < last || now - last < POLL_WAIT) return quarantine(session, RPI5_PCIE_LINK_CLOCK);
        if (now - start > POLL_LIMIT) return quarantine(session, RPI5_PCIE_LINK_TIMEOUT);
        last = now;
    }
    READ16(LINK_STATUS, result.negotiated);
    result.generation = result.negotiated & 0xf;
    result.lanes = (result.negotiated >> 4) & 0x3f;
    if ((result.generation != 1 && result.generation != 2) ||
        (result.lanes != 1 && result.lanes != 2 && result.lanes != 4) ||
        (result.negotiated & 0x800)) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    /* Revalidate stable configuration after the time-consuming wait and make
     * link status the last hardware read, after all provider checks. */
    READ(CAPABILITY, value);
    if (value != result.capability_after) return quarantine(session, RPI5_PCIE_LINK_READBACK);
    READ16(CONTROL2, half);
    if (half != result.control2_after) return quarantine(session, RPI5_PCIE_LINK_READBACK);
    READ(DEBUG, value);
    if (value != result.debug_after) return quarantine(session, RPI5_PCIE_LINK_READBACK);
    READ16(LINK_CONTROL, half);
    if (half & 0x103) return quarantine(session, RPI5_PCIE_LINK_PROFILE);
    READ(CONTROL, value);
    if (value != result.control_released) return quarantine(session, RPI5_PCIE_LINK_READBACK);
    STEP(session->io.check_lifecycle(io->context, 1));
    READ(STATUS, result.status_final);
    if ((result.status_final & 0xf0) != 0xb0) return quarantine(session, RPI5_PCIE_LINK_LOST);
#undef WRITE
#undef READ16
#undef READ
#undef STEP
    out->status_before = result.status_before;
    out->control_before = result.control_before;
    out->control_released = result.control_released;
    out->capability_before = result.capability_before;
    out->capability_after = result.capability_after;
    out->debug_before = result.debug_before;
    out->debug_after = result.debug_after;
    out->status_up = result.status_up;
    out->status_final = result.status_final;
    out->poll_reads = result.poll_reads;
    out->generation = result.generation;
    out->lanes = result.lanes;
    out->control2_before = result.control2_before;
    out->control2_after = result.control2_after;
    out->negotiated = result.negotiated;
    out->reset_wait_us = result.reset_wait_us;
    out->poll_elapsed_us = result.poll_elapsed_us;
    session->state = RPI5_PCIE_LINK_COMPLETE;
    return RPI5_PCIE_LINK_OK;
}
