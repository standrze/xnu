/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_qos.h"
static int dependencies(const struct rpi5_pcie_qos *s)
{
    if (!s->ubus || s->ubus->state != RPI5_PCIE_UBUS_COMPLETE || !s->ubus->serdes) return 0;
    const struct rpi5_pcie_serdes *p = s->ubus->serdes;
    const struct rpi5_pcie_mdio_io *io = &p->mdio.io;
    return p->state == RPI5_PCIE_SERDES_COMPLETE && p->mdio.state == RPI5_PCIE_MDIO_READY &&
        p->calibration && p->bridge_reset && p->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        p->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE &&
        io->physical_base == UINT64_C(0x1000120000) && io->mapped_bytes == 0x9310 &&
        io->read32 && io->write32 && io->order && s->check_owner;
}
int rpi5_pcie_qos_init(struct rpi5_pcie_qos *s, struct rpi5_pcie_ubus *ubus,
    const struct rpi5_pcie_profile *profile, int (*check_owner)(void *))
{
    if (!s || !profile || !check_owner) return RPI5_PCIE_QOS_ARGUMENT;
    if (s->state != RPI5_PCIE_QOS_EMPTY) return RPI5_PCIE_QOS_STATE;
    if (profile->generation != 2 || profile->lanes != 4 || profile->clkreq > RPI5_PCIE_CLKREQ_NO_L1SS ||
        profile->aspm_no_l0s > 1 || profile->qos_kind > RPI5_PCIE_QOS_VDM ||
        (profile->qos_kind == RPI5_PCIE_QOS_NONE && profile->qos_word) ||
        (profile->qos_kind == RPI5_PCIE_QOS_FIFO && profile->qos_word > 0xffff)) return RPI5_PCIE_QOS_ARGUMENT;
    struct rpi5_pcie_qos view = {0}; view.ubus = ubus; view.check_owner = check_owner;
    if (!dependencies(&view)) return RPI5_PCIE_QOS_DEPENDENCY;
    s->ubus = ubus; s->profile = *profile; s->check_owner = check_owner;
    s->completed_callbacks = 0; s->state = RPI5_PCIE_QOS_READY;
    return RPI5_PCIE_QOS_OK;
}
static int failed(struct rpi5_pcie_qos *s, int rc)
{
    s->state = RPI5_PCIE_QOS_QUARANTINED;
    if (s->ubus) {
        s->ubus->state = RPI5_PCIE_UBUS_QUARANTINED;
        if (s->ubus->serdes) {
            s->ubus->serdes->state = RPI5_PCIE_SERDES_QUARANTINED;
            s->ubus->serdes->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
        }
    }
    return rc;
}
static int owner(struct rpi5_pcie_qos *s)
{
    if (!dependencies(s)) return RPI5_PCIE_QOS_DEPENDENCY;
    if (s->check_owner(s->ubus->serdes->mdio.io.context)) return RPI5_PCIE_QOS_IO;
    s->completed_callbacks++;
    return dependencies(s) ? RPI5_PCIE_QOS_OK : RPI5_PCIE_QOS_DEPENDENCY;
}
static int read32(struct rpi5_pcie_qos *s, uint32_t offset, uint32_t *value)
{
    int rc = owner(s); if (rc) return rc;
    const struct rpi5_pcie_mdio_io *io = &s->ubus->serdes->mdio.io;
    if (io->read32(io->context, offset, value)) return RPI5_PCIE_QOS_IO;
    s->completed_callbacks++;
    rc = owner(s); if (rc) return rc;
    /* Full priority words can legitimately be all 15, and the two old vendor
     * ID fields may both be 0xffff. Do not mistake valid data for a bus error.
     * Independent status/control/AXI/debug reads still reject all ones. */
    return *value == UINT32_MAX && offset != 0x4164 && offset != 0x4168 && offset != 0x0a0c ?
        RPI5_PCIE_QOS_READBACK : RPI5_PCIE_QOS_OK;
}
static int quiescent(struct rpi5_pcie_qos *s, uint32_t enabled, uint32_t *control)
{
    uint32_t status, reset, debug, axi, ctrl; int rc;
    if ((rc = read32(s, 0x4068, &status)) || (rc = read32(s, 0x4064, &reset)) ||
        (rc = read32(s, 0x4304, &debug)) || (rc = read32(s, 0x416c, &axi)) ||
        (rc = read32(s, 0x40a0, &ctrl))) return rc;
    if ((status & 0xf0) != 0x80 || (reset & 5) || (debug & 0x08000000) ||
        (axi & 0x2880) != 0x2800 || (ctrl & 0x20) != enabled) return RPI5_PCIE_QOS_NOT_QUIESCENT;
    *control = ctrl; return RPI5_PCIE_QOS_OK;
}
static int write32(struct rpi5_pcie_qos *s, uint32_t offset, uint32_t value)
{
    int rc = owner(s); if (rc) return rc;
    const struct rpi5_pcie_mdio_io *io = &s->ubus->serdes->mdio.io;
    if (io->write32(io->context, offset, value)) return RPI5_PCIE_QOS_IO;
    s->completed_callbacks++;
    rc = owner(s); if (rc) return rc;
    if (io->order(io->context)) return RPI5_PCIE_QOS_IO;
    s->completed_callbacks++;
    return owner(s);
}
int rpi5_pcie_qos_configure(struct rpi5_pcie_qos *s, struct rpi5_pcie_qos_observation *out)
{
    if (!s || !out) return RPI5_PCIE_QOS_ARGUMENT;
    if (s->state != RPI5_PCIE_QOS_READY) return RPI5_PCIE_QOS_STATE;
    s->state = RPI5_PCIE_QOS_BUSY;
    uint32_t offsets[5], masks[5], wanted[5], count = 0, ctrl = 0;
    uint32_t kind = s->profile.qos_kind, word = s->profile.qos_word; int rc;
    /* FIFO has eight per-TC registers; handle these independently below. */
    if (kind == RPI5_PCIE_QOS_VDM) {
        offsets[0] = 0x4168; masks[0] = UINT32_MAX; wanted[0] = word;
        offsets[1] = 0x4164; masks[1] = UINT32_MAX; wanted[1] = word;
        offsets[2] = 0x0a0c; masks[2] = UINT32_MAX; wanted[2] = 0;
        offsets[3] = 0x0a20; masks[3] = 0x70000; wanted[3] = 0x70000;
        offsets[4] = 0x40a0; masks[4] = 0x20; wanted[4] = 0x20;
        count = 5;
    }
    uint32_t n = kind == RPI5_PCIE_QOS_FIFO ? 8 : count;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t off = kind == RPI5_PCIE_QOS_FIFO ? 0x4160 - 4*i : offsets[i];
        uint32_t mask = kind == RPI5_PCIE_QOS_FIFO ? 0xffff : masks[i];
        uint32_t bits = kind == RPI5_PCIE_QOS_FIFO ? word : wanted[i], before, after;
        rc = quiescent(s, 0, &ctrl); if (rc) return failed(s, rc);
        rc = read32(s, off, &before); if (rc) return failed(s, rc);
        rc = write32(s, off, (before & ~mask) | bits); if (rc) return failed(s, rc);
        rc = read32(s, off, &after); if (rc) return failed(s, rc);
        if ((after & mask) != bits) return failed(s, RPI5_PCIE_QOS_READBACK);
    }
    /* Independent final pass; preserve unrelated fields, verify target fields. */
    for (uint32_t i = 0; i < n; i++) {
        uint32_t value, off = kind == RPI5_PCIE_QOS_FIFO ? 0x4160 - 4*i : offsets[i];
        uint32_t mask = kind == RPI5_PCIE_QOS_FIFO ? 0xffff : masks[i];
        uint32_t bits = kind == RPI5_PCIE_QOS_FIFO ? word : wanted[i];
        rc = read32(s, off, &value); if (rc) return failed(s, rc);
        if ((value & mask) != bits) return failed(s, RPI5_PCIE_QOS_READBACK);
    }
    rc = quiescent(s, kind == RPI5_PCIE_QOS_VDM ? 0x20 : 0, &ctrl);
    if (rc) return failed(s, rc);
    rc = owner(s); if (rc) return failed(s, rc);
    struct rpi5_pcie_qos_observation result = {kind, word, n, ctrl, s->completed_callbacks};
    *out = result; s->state = RPI5_PCIE_QOS_COMPLETE;
    return RPI5_PCIE_QOS_OK;
}
