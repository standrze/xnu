/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_rc.h"

#define MISC UINT32_C(0x4008)
#define MISC_MASK UINT32_C(0x00303480)
#define MISC_VALUE UINT32_C(0x00203480)
#define CAPABILITY UINT32_C(0x04dc)
#define CLASS UINT32_C(0x043c)
#define ENDIAN UINT32_C(0x0188)
#define LINK_CONTROL UINT32_C(0x00bc)
#define STATUS UINT32_C(0x4068)
#define CONTROL UINT32_C(0x4064)

static int dependencies(const struct rpi5_pcie_rc *s,
    enum rpi5_pcie_windows_state windows_state)
{
    if (!s->windows || !s->bridge_reset || !s->calibration ||
        s->windows->state != windows_state ||
        s->bridge_reset->state != RPI5_PCIE_RESET_COMPLETE ||
        s->calibration->state != RPI5_PCIE_RESCAL_COMPLETE) return 0;
    const struct rpi5_pcie_windows_io *io = &s->windows->io;
    return io->physical_base == UINT64_C(0x1000120000) && io->mapped_bytes == 0x9310 &&
        io->check_quiescent && io->read32 && io->write32 && io->order &&
        s->io.read16 && s->io.write16;
}

int rpi5_pcie_rc_init(struct rpi5_pcie_rc *s, struct rpi5_pcie_windows *windows,
    const struct rpi5_pcie_reset *reset, const struct rpi5_pcie_rescal *rescal,
    const struct rpi5_pcie_rc_io *io)
{
    if (!s || !io || !io->read16 || !io->write16) return RPI5_PCIE_RC_ARGUMENT;
    if (s->state != RPI5_PCIE_RC_EMPTY) return RPI5_PCIE_RC_STATE;
    /* Build a temporary view so a rejected init leaves the session unchanged. */
    struct rpi5_pcie_rc view;
    view.windows = windows; view.bridge_reset = reset; view.calibration = rescal;
    view.io.read16 = io->read16; view.io.write16 = io->write16;
    if (!dependencies(&view, RPI5_PCIE_WINDOWS_READY)) return RPI5_PCIE_RC_DEPENDENCY;
    s->windows = windows; s->bridge_reset = reset; s->calibration = rescal;
    s->io.read16 = io->read16; s->io.write16 = io->write16;
    s->completed_callbacks = 0; s->last_windows_result = 0;
    s->state = RPI5_PCIE_RC_READY;
    return RPI5_PCIE_RC_OK;
}
static int quarantine(struct rpi5_pcie_rc *s, int rc)
{
    s->state = RPI5_PCIE_RC_QUARANTINED;
    if (s->windows) s->windows->state = RPI5_PCIE_WINDOWS_QUARANTINED;
    return rc;
}
static int read32(struct rpi5_pcie_rc *s, uint32_t reg, uint32_t *value)
{
    const struct rpi5_pcie_windows_io *io = &s->windows->io;
    if (io->read32(io->context, reg, value)) return RPI5_PCIE_RC_IO;
    s->completed_callbacks++;
    return *value == UINT32_MAX ? RPI5_PCIE_RC_READBACK : RPI5_PCIE_RC_OK;
}
static int read16(struct rpi5_pcie_rc *s, uint16_t *value)
{
    if (s->io.read16(s->windows->io.context, LINK_CONTROL, value)) return RPI5_PCIE_RC_IO;
    s->completed_callbacks++;
    return *value == UINT16_MAX ? RPI5_PCIE_RC_READBACK : RPI5_PCIE_RC_OK;
}
static int write32(struct rpi5_pcie_rc *s, uint32_t reg, uint32_t value)
{
    const struct rpi5_pcie_windows_io *io = &s->windows->io;
    if (io->write32(io->context, reg, value)) return RPI5_PCIE_RC_IO;
    s->completed_callbacks++;
    if (io->order(io->context)) return RPI5_PCIE_RC_IO;
    s->completed_callbacks++;
    uint32_t actual;
    int rc = read32(s, reg, &actual);
    if (rc) return rc;
    return actual == value ? RPI5_PCIE_RC_OK : RPI5_PCIE_RC_READBACK;
}
static int guard(struct rpi5_pcie_rc *s, uint32_t *status, uint32_t *control)
{
    if (s->windows->io.check_quiescent(s->windows->io.context))
        return RPI5_PCIE_RC_NOT_QUIESCENT;
    s->completed_callbacks++;
    int rc = read32(s, STATUS, status);
    if (rc) return rc;
    if ((*status & 0xf0) != 0x80) return RPI5_PCIE_RC_NOT_QUIESCENT;
    rc = read32(s, CONTROL, control);
    if (rc) return rc;
    return *control & 5 ? RPI5_PCIE_RC_NOT_QUIESCENT : RPI5_PCIE_RC_OK;
}

int rpi5_pcie_rc_configure(struct rpi5_pcie_rc *s, struct rpi5_pcie_rc_observation *out)
{
    if (!s || !out) return RPI5_PCIE_RC_ARGUMENT;
    if (s->state != RPI5_PCIE_RC_READY) return RPI5_PCIE_RC_STATE;
    s->state = RPI5_PCIE_RC_BUSY;
    if (!dependencies(s, RPI5_PCIE_WINDOWS_READY)) return quarantine(s, RPI5_PCIE_RC_DEPENDENCY);
    const struct rpi5_pcie_windows_io *io = &s->windows->io;
    struct rpi5_pcie_rc_observation r;
    uint32_t value, status, control;
    uint16_t half;
#define DO(call) do { int rc = (call); if (rc) return quarantine(s, rc); } while (0)
    DO(guard(s, &status, &control));
    DO(read32(s, CAPABILITY, &r.capability));
    if ((r.capability & 0x1f0) != 0x40) return quarantine(s, RPI5_PCIE_RC_PROFILE);
    DO(read32(s, MISC, &r.misc_before));
    r.misc_after = (r.misc_before & ~MISC_MASK) | MISC_VALUE;
    DO(write32(s, MISC, r.misc_after));
    DO(guard(s, &status, &control));
    struct rpi5_pcie_windows_observation windows;
    s->last_windows_result = rpi5_pcie_windows_program(s->windows, &windows);
    if (s->last_windows_result) return quarantine(s, RPI5_PCIE_RC_WINDOWS);
    if (!dependencies(s, RPI5_PCIE_WINDOWS_COMPLETE)) return quarantine(s, RPI5_PCIE_RC_DEPENDENCY);
    DO(guard(s, &status, &control));
    DO(read32(s, CLASS, &r.class_before));
    r.class_after = (r.class_before & ~UINT32_C(0xffffff)) | UINT32_C(0x060400);
    DO(write32(s, CLASS, r.class_after));
    DO(read32(s, ENDIAN, &r.endian_before));
    r.endian_after = r.endian_before & ~UINT32_C(0xc);
    DO(write32(s, ENDIAN, r.endian_after));
    DO(read16(s, &r.link_control_before));
    if (r.link_control_before & 0x30) return quarantine(s, RPI5_PCIE_RC_PROFILE);
    r.link_control_after = r.link_control_before & ~UINT16_C(0x103);
    if (s->io.write16(io->context, LINK_CONTROL, r.link_control_after))
        return quarantine(s, RPI5_PCIE_RC_IO);
    s->completed_callbacks++;
    if (io->order(io->context)) return quarantine(s, RPI5_PCIE_RC_IO);
    s->completed_callbacks++;
    DO(read16(s, &half));
    if (half != r.link_control_after) return quarantine(s, RPI5_PCIE_RC_READBACK);
    /* Independent final pass; reject cross-register aliases/late drift. */
    DO(read32(s, MISC, &value));
    if (value != r.misc_after) return quarantine(s, RPI5_PCIE_RC_READBACK);
    DO(read32(s, CAPABILITY, &value));
    if (value != r.capability) return quarantine(s, RPI5_PCIE_RC_READBACK);
    DO(read32(s, CLASS, &value));
    if (value != r.class_after) return quarantine(s, RPI5_PCIE_RC_READBACK);
    DO(read32(s, ENDIAN, &value));
    if (value != r.endian_after) return quarantine(s, RPI5_PCIE_RC_READBACK);
    DO(read16(s, &half));
    if (half != r.link_control_after) return quarantine(s, RPI5_PCIE_RC_READBACK);
    if (!dependencies(s, RPI5_PCIE_WINDOWS_COMPLETE)) return quarantine(s, RPI5_PCIE_RC_DEPENDENCY);
    DO(guard(s, &r.final_status, &r.final_control));
#undef DO
    /* Explicit copies avoid freestanding memcpy and publish only on success. */
    out->misc_before = r.misc_before; out->misc_after = r.misc_after;
    out->capability = r.capability;
    out->class_before = r.class_before; out->class_after = r.class_after;
    out->endian_before = r.endian_before; out->endian_after = r.endian_after;
    out->link_control_before = r.link_control_before;
    out->link_control_after = r.link_control_after;
    out->final_status = r.final_status; out->final_control = r.final_control;
    out->completed_callbacks = s->completed_callbacks;
    out->window_callbacks = windows.completed_callbacks;
    s->state = RPI5_PCIE_RC_COMPLETE;
    return RPI5_PCIE_RC_OK;
}
