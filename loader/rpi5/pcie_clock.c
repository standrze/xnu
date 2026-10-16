/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_clock.h"

#define CAP UINT32_C(0x04dc)
#define ROOT_CAP UINT32_C(0x04f8)
#define DEBUG UINT32_C(0x4304)
#define CLKREQ UINT32_C(0x00310002)
#define L1SS_MODE UINT32_C(0xf8)

static int base_dependencies(const struct rpi5_pcie_clock *s)
{
    if (!s->qos || s->qos->state != RPI5_PCIE_QOS_COMPLETE || !s->qos->ubus ||
        s->qos->ubus->state != RPI5_PCIE_UBUS_COMPLETE || !s->qos->ubus->serdes ||
        !s->qos->check_owner) return 0;
    const struct rpi5_pcie_serdes *p = s->qos->ubus->serdes;
    const struct rpi5_pcie_mdio_io *io = &p->mdio.io;
    return p->state == RPI5_PCIE_SERDES_COMPLETE && p->mdio.state == RPI5_PCIE_MDIO_READY &&
        p->bridge_reset && p->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE &&
        p->calibration && p->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        io->physical_base == UINT64_C(0x1000120000) && io->mapped_bytes == 0x9310 &&
        io->read32 && io->write32 && io->order;
}
static int link_dependencies(const struct rpi5_pcie_clock *s, const struct rpi5_pcie_link *l)
{
    if (!base_dependencies(s) || !l || l->state != RPI5_PCIE_LINK_COMPLETE ||
        l->ubus != s->qos->ubus || !l->windows || l->windows->state != RPI5_PCIE_WINDOWS_COMPLETE ||
        !l->io.rc || l->io.rc->state != RPI5_PCIE_RC_COMPLETE || l->io.rc->windows != l->windows ||
        !l->io.check_lifecycle || !l->io.read16 || !l->io.write16 ||
        l->io.rc->io.read16 != l->io.read16 || l->io.rc->io.write16 != l->io.write16) return 0;
    const struct rpi5_pcie_serdes *p = s->qos->ubus->serdes;
    const struct rpi5_pcie_mdio_io *io = &p->mdio.io;
    const struct rpi5_pcie_windows_io *w = &l->windows->io;
    return l->io.rc->bridge_reset == p->bridge_reset && l->io.rc->calibration == p->calibration &&
        w->context == io->context && w->physical_base == io->physical_base &&
        w->mapped_bytes == io->mapped_bytes && w->read32 == io->read32 &&
        w->write32 == io->write32 && w->order == io->order && w->check_quiescent;
}
static int dependencies(const struct rpi5_pcie_clock *s)
{ return s->link ? link_dependencies(s, s->link) : base_dependencies(s); }
int rpi5_pcie_clock_init(struct rpi5_pcie_clock *s, struct rpi5_pcie_qos *qos)
{
    if (!s || !qos) return RPI5_PCIE_CLOCK_ARGUMENT;
    if (s->state != RPI5_PCIE_CLOCK_EMPTY) return RPI5_PCIE_CLOCK_STATE;
    struct rpi5_pcie_clock view = {0}; view.qos = qos;
    if (!base_dependencies(&view)) return RPI5_PCIE_CLOCK_DEPENDENCY;
    if (qos->profile.generation != 2 || qos->profile.lanes != 4 ||
        qos->profile.clkreq > RPI5_PCIE_CLKREQ_NO_L1SS || qos->profile.aspm_no_l0s > 1)
        return RPI5_PCIE_CLOCK_PROFILE;
    s->qos = qos; s->link = 0; s->profile = qos->profile;
    s->completed_callbacks = 0; s->state = RPI5_PCIE_CLOCK_READY;
    return RPI5_PCIE_CLOCK_OK;
}
static int failed(struct rpi5_pcie_clock *s, int rc)
{
    s->state = RPI5_PCIE_CLOCK_QUARANTINED;
    if (s->qos) {
        s->qos->state = RPI5_PCIE_QOS_QUARANTINED;
        if (s->qos->ubus) {
            s->qos->ubus->state = RPI5_PCIE_UBUS_QUARANTINED;
            if (s->qos->ubus->serdes) {
                s->qos->ubus->serdes->state = RPI5_PCIE_SERDES_QUARANTINED;
                s->qos->ubus->serdes->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
            }
        }
    }
    if (s->link) {
        s->link->state = RPI5_PCIE_LINK_QUARANTINED;
        if (s->link->windows) s->link->windows->state = RPI5_PCIE_WINDOWS_QUARANTINED;
        if (s->link->io.rc) s->link->io.rc->state = RPI5_PCIE_RC_QUARANTINED;
    }
    return rc;
}
static int owner(struct rpi5_pcie_clock *s)
{
    if (!dependencies(s)) return RPI5_PCIE_CLOCK_DEPENDENCY;
    if (s->qos->check_owner(s->qos->ubus->serdes->mdio.io.context)) return RPI5_PCIE_CLOCK_IO;
    s->completed_callbacks++;
    return dependencies(s) ? RPI5_PCIE_CLOCK_OK : RPI5_PCIE_CLOCK_DEPENDENCY;
}
static int read32(struct rpi5_pcie_clock *s, uint32_t offset, uint32_t *out)
{
    int rc = owner(s); if (rc) return rc;
    const struct rpi5_pcie_mdio_io *io = &s->qos->ubus->serdes->mdio.io;
    if (io->read32(io->context, offset, out)) return RPI5_PCIE_CLOCK_IO;
    s->completed_callbacks++;
    rc = owner(s); if (rc) return rc;
    return *out == UINT32_MAX ? RPI5_PCIE_CLOCK_READBACK : RPI5_PCIE_CLOCK_OK;
}
static int write32(struct rpi5_pcie_clock *s, uint32_t offset, uint32_t value)
{
    int rc = owner(s); if (rc) return rc;
    const struct rpi5_pcie_mdio_io *io = &s->qos->ubus->serdes->mdio.io;
    if (io->write32(io->context, offset, value)) return RPI5_PCIE_CLOCK_IO;
    s->completed_callbacks++;
    rc = owner(s); if (rc) return rc;
    if (io->order(io->context)) return RPI5_PCIE_CLOCK_IO;
    s->completed_callbacks++;
    return owner(s);
}
static int lifecycle(struct rpi5_pcie_clock *s)
{
    int rc = owner(s); if (rc) return rc;
    const struct rpi5_pcie_mdio_io *io = &s->qos->ubus->serdes->mdio.io;
    if (s->link && s->link->io.check_lifecycle(io->context, 1)) return RPI5_PCIE_CLOCK_LIFECYCLE;
    if (s->link) { s->completed_callbacks++; rc = owner(s); if (rc) return rc; }
    uint32_t status, control, debug, axi;
    if ((rc = read32(s, 0x4068, &status)) || (rc = read32(s, 0x4064, &control)) ||
        (rc = read32(s, DEBUG, &debug)) || (rc = read32(s, 0x416c, &axi))) return rc;
    if ((status & 0xf0) != (s->link ? 0xb0u : 0x80u) ||
        (control & 5) != (s->link ? 4u : 0u) || (debug & 0x08000008) ||
        (axi & 0x2880) != 0x2800) return RPI5_PCIE_CLOCK_LIFECYCLE;
    if (s->link) {
        uint16_t half;
        rc = owner(s); if (rc) return rc;
        if (s->link->io.read16(io->context, 0xbc, &half)) return RPI5_PCIE_CLOCK_IO;
        s->completed_callbacks++;
        rc = owner(s); if (rc) return rc;
        /* Keep root ASPM/clock-PM disabled, no link-disable or retrain. */
        if (half == UINT16_MAX || (half & 0x133)) return RPI5_PCIE_CLOCK_PROFILE;
    }
    return RPI5_PCIE_CLOCK_OK;
}
int rpi5_pcie_clock_prepare(struct rpi5_pcie_clock *s, struct rpi5_pcie_clock_pre_observation *out)
{
    if (!s || !out) return RPI5_PCIE_CLOCK_ARGUMENT;
    if (s->state != RPI5_PCIE_CLOCK_READY) return RPI5_PCIE_CLOCK_STATE;
    s->state = RPI5_PCIE_CLOCK_BUSY;
    struct rpi5_pcie_clock_pre_observation result = {0}; uint32_t final; int rc;
    rc = lifecycle(s); if (rc) return failed(s, rc);
    rc = read32(s, CAP, &result.capability_before); if (rc) return failed(s, rc);
    if ((result.capability_before & 0x1f0) != 0x40) return failed(s, RPI5_PCIE_CLOCK_PROFILE);
    result.capability_after = result.capability_before & ~(s->profile.aspm_no_l0s ? 0x400u : 0u);
    if (s->profile.aspm_no_l0s) {
        rc = lifecycle(s); if (rc) return failed(s, rc);
        rc = write32(s, CAP, result.capability_after); if (rc) return failed(s, rc);
        result.writes = 1;
        rc = read32(s, CAP, &final); if (rc) return failed(s, rc);
        if (final != result.capability_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    }
    rc = read32(s, CAP, &final); if (rc) return failed(s, rc);
    if (final != result.capability_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    rc = lifecycle(s); if (rc) return failed(s, rc);
    rc = owner(s); if (rc) return failed(s, rc);
    result.completed_callbacks = s->completed_callbacks;
    *out = result; s->state = RPI5_PCIE_CLOCK_PREPARED;
    return RPI5_PCIE_CLOCK_OK;
}
int rpi5_pcie_clock_finish(struct rpi5_pcie_clock *s, struct rpi5_pcie_link *link,
    struct rpi5_pcie_clock_post_observation *out)
{
    if (!s || !out || !link) return RPI5_PCIE_CLOCK_ARGUMENT;
    if (s->state != RPI5_PCIE_CLOCK_PREPARED) return RPI5_PCIE_CLOCK_STATE;
    if (!link_dependencies(s, link)) return RPI5_PCIE_CLOCK_DEPENDENCY;
    s->link = link; s->state = RPI5_PCIE_CLOCK_BUSY; s->completed_callbacks = 0;
    struct rpi5_pcie_clock_post_observation result = {0}; uint32_t cap, final; int rc;
    result.declared_mode = s->profile.clkreq;
    result.effective_mode = s->profile.clkreq == RPI5_PCIE_CLKREQ_ABSENT ?
        RPI5_PCIE_CLKREQ_DEFAULT : s->profile.clkreq;
    rc = lifecycle(s); if (rc) return failed(s, rc);
    rc = read32(s, CAP, &cap); if (rc) return failed(s, rc);
    if ((cap & 0x1ff) != 0x42 || (s->profile.aspm_no_l0s && (cap & 0x400)))
        return failed(s, RPI5_PCIE_CLOCK_PROFILE);
    rc = read32(s, ROOT_CAP, &result.root_before); if (rc) return failed(s, rc);
    rc = read32(s, DEBUG, &result.debug_before); if (rc) return failed(s, rc);
    /* Actual link trainer must have cleared all clock overrides before release. */
    if (result.debug_before & CLKREQ) return failed(s, RPI5_PCIE_CLOCK_PROFILE);
    result.root_after = result.root_before;
    result.debug_after = result.debug_before;
    if (result.effective_mode == RPI5_PCIE_CLKREQ_DEFAULT) result.debug_after |= 0x200000;
    else {
        result.root_after = (result.root_before & ~L1SS_MODE) | 0x10;
        result.debug_after |= result.effective_mode == RPI5_PCIE_CLKREQ_SAFE ? 0x110000 : 2;
        rc = lifecycle(s); if (rc) return failed(s, rc);
        rc = write32(s, ROOT_CAP, result.root_after); if (rc) return failed(s, rc);
        result.writes++;
        rc = read32(s, ROOT_CAP, &final); if (rc) return failed(s, rc);
        if (final != result.root_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    }
    rc = lifecycle(s); if (rc) return failed(s, rc);
    rc = write32(s, DEBUG, result.debug_after); if (rc) return failed(s, rc);
    result.writes++;
    rc = read32(s, DEBUG, &final); if (rc) return failed(s, rc);
    if (final != result.debug_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    rc = read32(s, ROOT_CAP, &final); if (rc) return failed(s, rc);
    if (final != result.root_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    rc = read32(s, DEBUG, &final); if (rc) return failed(s, rc);
    if (final != result.debug_after) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    rc = read32(s, CAP, &final); if (rc) return failed(s, rc);
    if (final != cap) return failed(s, RPI5_PCIE_CLOCK_READBACK);
    rc = lifecycle(s); if (rc) return failed(s, rc);
    rc = read32(s, 0x4068, &result.final_status); if (rc) return failed(s, rc);
    if ((result.final_status & 0xf0) != 0xb0) return failed(s, RPI5_PCIE_CLOCK_LIFECYCLE);
    rc = owner(s); if (rc) return failed(s, rc);
    result.completed_callbacks = s->completed_callbacks;
    *out = result; s->state = RPI5_PCIE_CLOCK_COMPLETE;
    return RPI5_PCIE_CLOCK_OK;
}
#undef L1SS_MODE
#undef CLKREQ
#undef DEBUG
#undef ROOT_CAP
#undef CAP
