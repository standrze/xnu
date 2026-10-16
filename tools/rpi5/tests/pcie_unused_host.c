/* SPDX-License-Identifier: BSD-2-Clause */
/* Callback/register model, not physical ownership or MMIO evidence. */
#include "pcie_unused.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_unused session;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_reset reset;
    unsigned calls, reads, fail_at, bad_read, drift_index, drift_at;
    unsigned dependency_at, mutate_index, mutate_at;
    uint32_t values[23], mutation;
};
static const uint32_t offsets[23] = {
    0x4068, 0x4064, 0x4304,
    0x40d4, 0x410c, 0x40dc, 0x4114, 0x40e4, 0x411c,
    0x40ec, 0x4124, 0x40f4, 0x412c, 0x40fc, 0x4134, 0x4104, 0x413c,
    0x4078, 0x4090, 0x4094, 0x407c, 0x4098, 0x409c
};
static int step(struct model *m)
{
    assert(m->session.state == RPI5_PCIE_UNUSED_BUSY);
    m->calls++;
    struct rpi5_pcie_unused_observation out;
    assert(rpi5_pcie_unused_inspect(&m->session, &out) == RPI5_PCIE_UNUSED_STATE);
    assert(rpi5_pcie_unused_init(&m->session, &m->ubus, &m->session.io) == RPI5_PCIE_UNUSED_STATE);
    if (m->calls == m->dependency_at) m->reset.state = RPI5_PCIE_RESET_QUARANTINED;
    return m->calls == m->fail_at;
}
static int check_owner(void *p) { return step(p) ? -1 : 0; }
static int read32(void *p, uint32_t offset, uint32_t *out)
{
    struct model *m = p;
    if (step(m)) return -1;
    unsigned index = m->reads++ % 23;
    assert(offset == offsets[index]); /* Exact order; no active windows/config/MSI/DMA. */
    *out = m->values[index];
    if (m->reads == m->bad_read) *out = UINT32_MAX;
    if (m->reads > 23 && index == m->drift_index && m->drift_at) *out ^= m->drift_at;
    if (m->reads > 23 && index == m->mutate_index && m->mutate_at) *out ^= m->mutation;
    return 0;
}
static int different_read(void *p, uint32_t off, uint32_t *out) { return read32(p, off, out); }
static void prepare(struct model *m)
{
    memset(m, 0, sizeof *m);
    m->reset.state = RPI5_PCIE_RESET_COMPLETE;
    m->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    m->serdes.state = RPI5_PCIE_SERDES_COMPLETE;
    m->serdes.mdio.state = RPI5_PCIE_MDIO_READY;
    m->serdes.calibration = &m->rescal;
    m->serdes.bridge_reset = &m->reset;
    m->serdes.mdio.io.context = m;
    m->serdes.mdio.io.read32 = read32;
    m->serdes.mdio.io.physical_base = UINT64_C(0x1000120000);
    m->serdes.mdio.io.mapped_bytes = 0x9310;
    m->ubus.state = RPI5_PCIE_UBUS_COMPLETE;
    m->ubus.serdes = &m->serdes;
    struct rpi5_pcie_unused_io io = {m, UINT64_C(0x1000120000), 0x9310, check_owner, read32};
    assert(!rpi5_pcie_unused_init(&m->session, &m->ubus, &io));
    assert(m->session.state == RPI5_PCIE_UNUSED_READY && !m->calls);
    m->values[0] = 0x80;
    /* BAR sizes zero with retained address bits; enabled UBUS remap is legal. */
    for (unsigned i = 0; i < 7; i++) {
        m->values[3 + 2*i] = 0xabc00000;
        m->values[4 + 2*i] = 0x12345001;
    }
    /* Low base 1 MiB, inclusive limit 1 MiB-1: disabled, not base==limit. */
    m->values[17] = m->values[20] = 0x10;
}
static void rejects(struct model *m, int expected)
{
    struct rpi5_pcie_unused_observation out, before;
    memset(&out, 0xa5, sizeof out); before = out;
    assert(rpi5_pcie_unused_inspect(&m->session, &out) == expected);
    assert(!memcmp(&out, &before, sizeof out));
    assert(m->session.state == RPI5_PCIE_UNUSED_QUARANTINED);
    assert(m->ubus.state == RPI5_PCIE_UBUS_QUARANTINED);
    assert(m->serdes.state == RPI5_PCIE_SERDES_QUARANTINED);
    assert(m->serdes.mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_unused_inspect(&m->session, &out) == RPI5_PCIE_UNUSED_STATE);
    assert(rpi5_pcie_unused_init(&m->session, &m->ubus, &m->session.io) == RPI5_PCIE_UNUSED_STATE);
    assert(calls == m->calls); /* Failure never causes cleanup writes or retry. */
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_unused_observation out;
    prepare(&m);
    assert(!rpi5_pcie_unused_inspect(&m.session, &out));
    assert(m.calls == 139 && m.reads == 46 && out.completed_callbacks == 139);
    assert(m.session.state == RPI5_PCIE_UNUSED_COMPLETE && out.remap_enabled_mask == 0x7f);
    assert(out.inbound_bar_lo[6] == 0xabc00000 && out.inbound_remap_lo[6] == 0x12345001);
    assert(out.outbound_base_limit[1] == 0x10 && out.final_status == 0x80);
    assert(rpi5_pcie_unused_inspect(&m.session, &out) == RPI5_PCIE_UNUSED_STATE);
    assert(m.calls == 139);
    for (unsigned fail = 1; fail <= 139; fail++) {
        prepare(&m); m.fail_at = fail;
        rejects(&m, RPI5_PCIE_UNUSED_IO);
        assert(m.calls == fail && m.session.completed_callbacks == fail-1);
    }
    for (unsigned bad = 1; bad <= 46; bad++) {
        prepare(&m); m.bad_read = bad;
        rejects(&m, RPI5_PCIE_UNUSED_IO); assert(m.reads == bad);
    }
    for (unsigned at = 1; at <= 139; at++) {
        prepare(&m); m.dependency_at = at;
        rejects(&m, RPI5_PCIE_UNUSED_DEPENDENCY); assert(m.calls == at);
    }
    for (unsigned index = 3; index < 23; index++) {
        prepare(&m); m.drift_index = index;
        /* Change only reserved bits/address while retaining disabled status. */
        m.drift_at = index < 17 ? 0x10000 : 0x100;
        rejects(&m, RPI5_PCIE_UNUSED_DRIFT); assert(m.reads == 46);
    }
    for (unsigned slot = 0; slot < 7; slot++)
    for (unsigned size = 1; size < 32; size++) {
        prepare(&m); m.values[3+2*slot] |= size;
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE);
    }
    const uint32_t status_bad[] = {0, 0x90, 0xa0, 0xc0};
    for (unsigned i = 0; i < 4; i++) {
        prepare(&m); m.values[0] = status_bad[i]; rejects(&m, RPI5_PCIE_UNUSED_ACTIVE);
    }
    for (unsigned i = 0; i < 3; i++) {
        prepare(&m); m.values[i ? i : 1] |= i == 2 ? 0x08000000 : (i ? 4 : 1);
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE);
        /* Required predicates must hold in the second snapshot too. */
        prepare(&m); m.mutate_at = 1; m.mutate_index = i;
        m.mutation = i == 0 ? 0x10 : i == 1 ? 4 : 0x08000000;
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE);
    }
    /* Unrelated status/control/debug changes are not window drift. */
    for (unsigned i = 0; i < 3; i++) {
        prepare(&m); m.mutate_at = 1; m.mutate_index = i; m.mutation = 0x10000;
        assert(!rpi5_pcie_unused_inspect(&m.session, &out));
    }
    for (unsigned slot = 0; slot < 2; slot++) {
        unsigned index = 17 + 3*slot;
        prepare(&m); m.values[index] = 0; /* All zero is ACTIVE, not disabled. */
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE);
        prepare(&m); m.values[index] = 0xfff0; m.values[index+2] = 1;
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE); /* Nonzero high limit defeats low-only check. */
        prepare(&m); m.values[index] = 0; m.values[index+1] = 1;
        assert(!rpi5_pcie_unused_inspect(&m.session, &out)); /* Nonzero high base disables. */
        prepare(&m); m.values[index] = 0xfffffff0; m.values[index+1] = m.values[index+2] = 0xff;
        rejects(&m, RPI5_PCIE_UNUSED_ACTIVE); /* Last inclusive MiB is still enabled. */
        prepare(&m); m.values[index+1] = 0xffffff00; m.values[index+2] = 0xabcdef00;
        assert(!rpi5_pcie_unused_inspect(&m.session, &out)); /* High-byte masks, not full 32 bits. */
    }
    for (unsigned bad = 0; bad < 16; bad++) {
        prepare(&m); struct rpi5_pcie_unused_io io = m.session.io;
        memset(&m.session, 0, sizeof m.session);
        if (bad == 0) m.ubus.state = RPI5_PCIE_UBUS_READY;
        if (bad == 1) m.ubus.serdes = 0;
        if (bad == 2) m.serdes.state = RPI5_PCIE_SERDES_READY;
        if (bad == 3) m.serdes.mdio.state = RPI5_PCIE_MDIO_BUSY;
        if (bad == 4) m.serdes.calibration = 0;
        if (bad == 5) m.serdes.bridge_reset = 0;
        if (bad == 6) io.physical_base++;
        if (bad == 7) io.mapped_bytes--;
        if (bad == 8) io.context = &m.reset;
        if (bad == 9) io.read32 = different_read;
        if (bad == 10) io.check_owner = 0;
        if (bad == 11) io.read32 = 0;
        if (bad == 12) m.serdes.mdio.io.physical_base++;
        if (bad == 13) m.serdes.mdio.io.mapped_bytes--;
        if (bad == 14) m.rescal.state = RPI5_PCIE_RESCAL_QUARANTINED;
        if (bad == 15) m.reset.state = RPI5_PCIE_RESET_QUARANTINED;
        struct rpi5_pcie_unused before = m.session;
        assert(rpi5_pcie_unused_init(&m.session, &m.ubus, &io) == RPI5_PCIE_UNUSED_DEPENDENCY);
        assert(!memcmp(&m.session, &before, sizeof before) && !m.calls);
    }
    prepare(&m);
    assert(rpi5_pcie_unused_init(0, &m.ubus, &m.session.io) == RPI5_PCIE_UNUSED_ARGUMENT);
    assert(rpi5_pcie_unused_init(&m.session, &m.ubus, 0) == RPI5_PCIE_UNUSED_ARGUMENT);
    assert(rpi5_pcie_unused_inspect(0, &out) == RPI5_PCIE_UNUSED_ARGUMENT);
    assert(rpi5_pcie_unused_inspect(&m.session, 0) == RPI5_PCIE_UNUSED_ARGUMENT);
    assert(!m.calls && m.session.state == RPI5_PCIE_UNUSED_READY);
    struct rpi5_pcie_unused empty = {0}, before = empty;
    assert(rpi5_pcie_unused_init(&empty, 0, &m.session.io) == RPI5_PCIE_UNUSED_DEPENDENCY);
    assert(!memcmp(&empty, &before, sizeof empty) && !m.calls);
    puts("PCIE_UNUSED_HOST_PASS CALLBACK_FAILURES=139 READ_FAILURES=46 DEPENDENCY_FAILURES=139 NO_MMIO=1");
    return 0;
}
