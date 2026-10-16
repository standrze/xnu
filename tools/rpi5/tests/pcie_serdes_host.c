/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_serdes.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_serdes *session;
    unsigned calls, fail_at, bad_at, wrong_bit_at, mdio_commands, data_writes;
    unsigned settle_waits;
    uint32_t hard_debug, phy_control, command, data;
    uint64_t now;
};
static int step(struct model *m)
{
    assert(m->session->state == RPI5_PCIE_SERDES_BUSY);
    m->calls++;
    struct rpi5_pcie_serdes_observation unused;
    assert(rpi5_pcie_serdes_configure54(m->session, &unused) == RPI5_PCIE_SERDES_STATE);
    return m->calls == m->fail_at;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    if (step(m)) return -1;
    switch (offset) {
        case 0x4304:
            *value = m->hard_debug;
            if (m->calls == m->wrong_bit_at) *value |= 0x08000000;
            break;
        case 0x184c:
            *value = m->phy_control;
            if (m->calls == m->wrong_bit_at) *value ^= 1;
            break;
        case 0x1100: *value = m->command; break;
        case 0x1104: *value = m->data & 0xffff; break;
        default: assert(0); /* no config selector, RD_DATA or other MMIO */
    }
    if (m->calls == m->bad_at) *value = UINT32_MAX;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    static const unsigned regs[] = {0x1f, 0x16, 0x17, 0x18, 0x19, 0x1b, 0x1c, 0x1e};
    static const unsigned values[] = {0x1600, 0x50b9, 0xbda1, 0x0094, 0x97b4, 0x5030, 0x5030, 0x0007};
    struct model *m = context;
    int failed = step(m);
    switch (offset) {
        case 0x4304:
            assert(value == (m->hard_debug & ~0x08000000u));
            m->hard_debug = value;
            break;
        case 0x184c:
            assert(value == ((m->phy_control & ~0xffu) | 0x12));
            m->phy_control = value;
            break;
        case 0x1100:
            assert(m->mdio_commands < 8 && value == regs[m->mdio_commands]);
            m->command = value; m->mdio_commands++;
            break;
        case 0x1104:
            assert(m->data_writes < 8 && value == (0x80000000u | values[m->data_writes]));
            m->data = value; m->data_writes++;
            break;
        default: assert(0);
    }
    return failed ? -1 : 0; /* don't undo writes which report failure */
}
static int order(void *context) { return step(context) ? -1 : 0; }
static int now_us(void *context, uint64_t *value)
{
    struct model *m = context;
    if (step(m)) return -1;
    *value = m->now; return 0;
}
static int delay_us(void *context, uint32_t value)
{
    struct model *m = context;
    if (step(m)) return -1;
    assert(value == 100); /* MDIO model completes on first poll */
    m->settle_waits++; m->now += value; return 0;
}
static struct rpi5_pcie_fdt topology(void)
{
    struct rpi5_pcie_fdt fdt = {0};
    fdt.bridge_regs = (struct rpi5_range){0x1000120000, 0x1000129310};
    return fdt;
}
static struct rpi5_pcie_mdio_io provider(struct model *m)
{
    struct rpi5_pcie_mdio_io io = {
        m, 0x1000120000, 0x9310, read32, write32, order, now_us, delay_us
    };
    return io;
}
static void prepare(struct model *m, struct rpi5_pcie_serdes *session,
    struct rpi5_pcie_rescal *calibration, struct rpi5_pcie_reset *reset)
{
    memset(m, 0, sizeof *m); memset(session, 0, sizeof *session);
    memset(calibration, 0, sizeof *calibration); memset(reset, 0, sizeof *reset);
    /* Explicit model prerequisites, not evidence of real calibration/reset. */
    calibration->state = RPI5_PCIE_RESCAL_COMPLETE;
    reset->state = RPI5_PCIE_RESET_COMPLETE;
    m->session = session; m->hard_debug = 0x8f123456; m->phy_control = 0x0088a5ff;
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_mdio_io io = provider(m);
    assert(!rpi5_pcie_serdes_init(session, &fdt, &io, calibration, reset));
    assert(!m->calls && session->state == RPI5_PCIE_SERDES_READY);
}
static void rejects(struct model *m, int rc)
{
    struct rpi5_pcie_serdes_observation out, before;
    memset(&out, 0xa5, sizeof out); before = out;
    assert(rpi5_pcie_serdes_configure54(m->session, &out) == rc);
    assert(!memcmp(&out, &before, sizeof out));
    assert(m->session->state == RPI5_PCIE_SERDES_QUARANTINED);
    assert(m->session->mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_serdes_configure54(m->session, &out) == RPI5_PCIE_SERDES_STATE);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_mdio_io io = provider(m);
    assert(rpi5_pcie_serdes_init(m->session, &fdt, &io, m->session->calibration,
                               m->session->bridge_reset) == RPI5_PCIE_SERDES_STATE);
    assert(m->calls == calls);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_serdes session;
    struct rpi5_pcie_rescal calibration;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_serdes_observation out;
    prepare(&m, &session, &calibration, &reset);
    assert(!rpi5_pcie_serdes_configure54(&session, &out));
    assert(m.calls == 82 && session.completed_actions == 18);
    assert(m.mdio_commands == 8 && m.data_writes == 8 && m.settle_waits == 2);
    assert(out.hard_debug_before == 0x8f123456 && out.hard_debug_after == 0x87123456);
    assert(out.phy_control_before == 0x0088a5ff && out.phy_control_after == 0x0088a512);
    assert(out.mdio_writes_completed == 8 && out.mdio_poll_reads == 8);
    assert(session.state == RPI5_PCIE_SERDES_COMPLETE && !session.last_mdio_result);
    assert(rpi5_pcie_serdes_configure54(&session, &out) == RPI5_PCIE_SERDES_STATE);
    assert(m.calls == 82);
    for (unsigned fail = 1; fail <= 82; fail++) {
        prepare(&m, &session, &calibration, &reset); m.fail_at = fail;
        int mdio = fail >= 6 && fail <= 77;
        rejects(&m, mdio ? RPI5_PCIE_SERDES_MDIO : RPI5_PCIE_SERDES_IO);
        assert(m.calls == fail);
        assert(session.last_mdio_result == (mdio ? RPI5_PCIE_MDIO_IO : RPI5_PCIE_MDIO_OK));
    }
    const unsigned bad_reads[] = {1, 5, 79, 82};
    for (unsigned i = 0; i < 4; i++) {
        prepare(&m, &session, &calibration, &reset); m.bad_at = bad_reads[i];
        rejects(&m, RPI5_PCIE_SERDES_READBACK); assert(m.calls == bad_reads[i]);
    }
    for (unsigned i = 0; i < 8; i++) {
        prepare(&m, &session, &calibration, &reset); m.bad_at = 13 + 9 * i;
        rejects(&m, RPI5_PCIE_SERDES_MDIO);
        assert(m.calls == m.bad_at && session.last_mdio_result == RPI5_PCIE_MDIO_READBACK);
    }
    prepare(&m, &session, &calibration, &reset); m.wrong_bit_at = 5;
    rejects(&m, RPI5_PCIE_SERDES_READBACK); assert(m.calls == 5);
    prepare(&m, &session, &calibration, &reset); m.wrong_bit_at = 82;
    rejects(&m, RPI5_PCIE_SERDES_READBACK); assert(m.calls == 82);
    for (unsigned bad = 0; bad < 3; bad++) {
        prepare(&m, &session, &calibration, &reset);
        if (bad == 0) calibration.state = RPI5_PCIE_RESCAL_QUARANTINED;
        if (bad == 1) reset.state = RPI5_PCIE_RESET_QUARANTINED;
        if (bad == 2) session.mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
        rejects(&m, RPI5_PCIE_SERDES_DEPENDENCY); assert(!m.calls);
    }
    prepare(&m, &session, &calibration, &reset);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_mdio_io io = provider(&m);
    memset(&session, 0, sizeof session);
    struct rpi5_pcie_serdes before = session;
    calibration.state = RPI5_PCIE_RESCAL_READY;
    assert(rpi5_pcie_serdes_init(&session, &fdt, &io, &calibration, &reset) == RPI5_PCIE_SERDES_DEPENDENCY);
    assert(!memcmp(&session, &before, sizeof session) && !m.calls);
    calibration.state = RPI5_PCIE_RESCAL_COMPLETE; io.physical_base++;
    assert(rpi5_pcie_serdes_init(&session, &fdt, &io, &calibration, &reset) == RPI5_PCIE_SERDES_ARGUMENT);
    assert(!memcmp(&session, &before, sizeof session) && !m.calls);
    assert(rpi5_pcie_serdes_configure54(NULL, &out) == RPI5_PCIE_SERDES_ARGUMENT);
    assert(rpi5_pcie_serdes_configure54(&session, NULL) == RPI5_PCIE_SERDES_ARGUMENT);
    puts("PCIE_SERDES_HOST_PASS");
    return 0;
}
