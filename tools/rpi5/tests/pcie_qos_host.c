/* SPDX-License-Identifier: BSD-2-Clause */
/* Callback model only; synthetic prerequisite states are NOT board evidence. */
#include "pcie_qos.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
    struct rpi5_pcie_qos s;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal rescal;
    unsigned calls, reads, writes, fail_at, dependency_at, bad_read, wrong_read, changed_read;
    uint32_t control, status, perst, debug, axi, fifo[8], low, high, vendor, vdm;
    uint32_t last_offset, wrong_mask;
};
static int step(struct model *m)
{
    assert(m->s.state == RPI5_PCIE_QOS_BUSY);
    struct rpi5_pcie_qos_observation out;
    assert(rpi5_pcie_qos_configure(&m->s, &out) == RPI5_PCIE_QOS_STATE);
    ++m->calls;
    if (m->calls == m->dependency_at) m->reset.state = RPI5_PCIE_RESET_QUARANTINED;
    return m->calls == m->fail_at;
}
static int owner(void *p) { return step(p) ? -1 : 0; }
static uint32_t *reg(struct model *m, uint32_t off)
{
    switch (off) {
        case 0x4068: return &m->status;
        case 0x4064: return &m->perst;
        case 0x4304: return &m->debug;
        case 0x416c: return &m->axi;
        case 0x40a0: return &m->control;
        case 0x4168: return &m->low;
        case 0x4164: return &m->high;
        case 0x0a0c: return &m->vendor;
        case 0x0a20: return &m->vdm;
        default:
            assert(off >= 0x4144 && off <= 0x4160 && !(off & 3));
            return &m->fifo[(0x4160-off)/4];
    }
}
static int read32(void *p, uint32_t off, uint32_t *out)
{
    struct model *m = p;
    if (step(m)) return -1;
    m->reads++;
    *out = *reg(m, off);
    if (m->reads == m->bad_read) *out = UINT32_MAX;
    if (m->reads == m->wrong_read) *out ^= m->wrong_mask ? m->wrong_mask : 1;
    if (m->reads == m->changed_read) m->perst |= 4;
    m->last_offset = off;
    return 0;
}
static int write32(void *p, uint32_t off, uint32_t value)
{
    struct model *m = p;
    int rc = step(m);
    /* No status/control-of-PERST/debug/AXI/config/IRQ/DMA writes. */
    if (m->s.profile.qos_kind == RPI5_PCIE_QOS_FIFO) {
        assert(off == 0x4160 - 4*m->writes);
        assert((value & 0xffff0000) == 0xabcd0000);
    } else {
        const uint32_t expected[] = {0x4168,0x4164,0x0a0c,0x0a20,0x40a0};
        assert(m->s.profile.qos_kind == RPI5_PCIE_QOS_VDM && m->writes < 5);
        assert(off == expected[m->writes]);
        if (off == 0x40a0) {
            assert(m->low == m->s.profile.qos_word && m->high == m->s.profile.qos_word);
            assert(m->vendor == 0 && (m->vdm & 0x70000) == 0x70000);
        }
    }
    ++m->writes; *reg(m, off) = value;
    return rc ? -1 : 0; /* A failed write can already have taken effect. */
}
static int order(void *p) { return step(p) ? -1 : 0; }
static void prepare(struct model *m, unsigned kind, uint32_t word)
{
    memset(m, 0, sizeof *m);
    m->ubus.state = RPI5_PCIE_UBUS_COMPLETE; m->ubus.serdes = &m->serdes;
    m->serdes.state = RPI5_PCIE_SERDES_COMPLETE; m->serdes.mdio.state = RPI5_PCIE_MDIO_READY;
    m->reset.state = RPI5_PCIE_RESET_COMPLETE; m->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    m->serdes.bridge_reset = &m->reset; m->serdes.calibration = &m->rescal;
    m->serdes.mdio.io = (struct rpi5_pcie_mdio_io){m,UINT64_C(0x1000120000),0x9310,read32,write32,order,0,0};
    struct rpi5_pcie_profile profile = {2,4,0,0,kind,word};
    assert(!rpi5_pcie_qos_init(&m->s, &m->ubus, &profile, owner));
    assert(!m->calls);
    m->status = 0x80; m->axi = 0x2800; m->control = 0x12340001;
    m->vdm = 0x80000001; m->vendor = UINT32_MAX;
    for (unsigned i = 0; i < 8; i++) m->fifo[i] = 0xabcd1111;
}
static void reject(struct model *m, int expected)
{
    struct rpi5_pcie_qos_observation out, before;
    memset(&out, 0xa5, sizeof out); before = out;
    assert(rpi5_pcie_qos_configure(&m->s, &out) == expected);
    assert(!memcmp(&out, &before, sizeof out));
    assert(m->s.state == RPI5_PCIE_QOS_QUARANTINED && m->ubus.state == RPI5_PCIE_UBUS_QUARANTINED);
    assert(m->serdes.state == RPI5_PCIE_SERDES_QUARANTINED && m->serdes.mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    unsigned calls = m->calls, writes = m->writes;
    assert(rpi5_pcie_qos_configure(&m->s, &out) == RPI5_PCIE_QOS_STATE);
    assert(rpi5_pcie_qos_init(&m->s, &m->ubus, &m->s.profile, owner) == RPI5_PCIE_QOS_STATE);
    assert(calls == m->calls && writes == m->writes);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_qos_observation out;
    unsigned failures = 0;
    const uint32_t words[] = {0,0x4321,0xbbaa9888};
    const unsigned counts[] = {16,248,161};
    for (unsigned kind = 0; kind < 3; kind++) {
        prepare(&m, kind, words[kind]);
        assert(!rpi5_pcie_qos_configure(&m.s, &out));
        assert(m.calls == counts[kind] && out.completed_callbacks == m.calls && m.calls <= 256);
        assert(m.writes == (kind == 1 ? 8u : kind == 2 ? 5u : 0u));
        assert(out.registers_programmed == m.writes && out.kind == kind && out.word == words[kind]);
        assert(m.s.state == RPI5_PCIE_QOS_COMPLETE);
        if (kind == 1) for (unsigned i = 0; i < 8; i++) assert(m.fifo[i] == 0xabcd4321);
        if (kind == 2) assert(m.low == words[kind] && m.high == words[kind] && m.vdm == 0x80070001);
        for (unsigned fail = 1; fail <= counts[kind]; fail++) {
            prepare(&m, kind, words[kind]); m.fail_at = fail;
            reject(&m, RPI5_PCIE_QOS_IO); assert(m.calls == fail && m.s.completed_callbacks == fail-1);
            failures++;
            prepare(&m, kind, words[kind]); m.dependency_at = fail;
            reject(&m, RPI5_PCIE_QOS_DEPENDENCY); assert(m.calls == fail);
        }
        unsigned n = kind == 1 ? 8 : kind == 2 ? 5 : 0;
        for (unsigned target = 0; target < n; target++)
        for (unsigned final = 0; final < 2; final++) {
            prepare(&m, kind, words[kind]);
            m.wrong_read = final ? 7*n + target + 1 : 7*(target+1);
            m.wrong_mask = kind == 2 && target == 3 ? 0x10000 : kind == 2 && target == 4 ? 0x20 : 1;
            reject(&m, RPI5_PCIE_QOS_READBACK);
            assert(m.writes == (final ? n : target+1));
        }
    }
    prepare(&m, 2, UINT32_MAX); assert(!rpi5_pcie_qos_configure(&m.s, &out));
    assert(m.low == UINT32_MAX && m.high == UINT32_MAX); /* Legal priorities all 15. */
    for (unsigned bad = 0; bad < 7; bad++) {
        prepare(&m, 2, words[2]);
        if (bad == 0) m.status |= 0x10;
        if (bad == 1) m.status &= ~0x80u;
        if (bad == 2) m.perst |= 4;
        if (bad == 3) m.perst |= 1;
        if (bad == 4) m.debug |= 0x08000000;
        if (bad == 5) m.axi &= ~0x2000u;
        if (bad == 6) m.control |= 0x20;
        reject(&m, RPI5_PCIE_QOS_NOT_QUIESCENT); assert(!m.writes);
    }
    prepare(&m, 1, words[1]); m.bad_read = 1;
    reject(&m, RPI5_PCIE_QOS_READBACK); assert(!m.writes);
    prepare(&m, 1, words[1]); m.wrong_read = 7; /* First target readback. */
    reject(&m, RPI5_PCIE_QOS_READBACK); assert(m.writes == 1);
    prepare(&m, 1, words[1]); m.wrong_read = 57; /* First final-pass target. */
    reject(&m, RPI5_PCIE_QOS_READBACK); assert(m.writes == 8);
    prepare(&m, 2, words[2]); m.changed_read = 7;
    reject(&m, RPI5_PCIE_QOS_NOT_QUIESCENT); assert(m.writes == 1);
    prepare(&m, 0, 0);
    assert(rpi5_pcie_qos_configure(&m.s, 0) == RPI5_PCIE_QOS_ARGUMENT && !m.calls);
    struct rpi5_pcie_qos empty = {0}, before = empty;
    m.reset.state = RPI5_PCIE_RESET_QUARANTINED;
    assert(rpi5_pcie_qos_init(&empty, &m.ubus, &m.s.profile, owner) == RPI5_PCIE_QOS_DEPENDENCY);
    assert(!memcmp(&empty, &before, sizeof empty) && !m.calls);
    for (unsigned bad = 0; bad < 7; bad++) {
        prepare(&m, 0, 0); memset(&empty, 0, sizeof empty);
        struct rpi5_pcie_profile profile = m.s.profile;
        if (bad == 0) profile.generation = 3;
        if (bad == 1) profile.lanes = 1;
        if (bad == 2) profile.clkreq = 4;
        if (bad == 3) profile.aspm_no_l0s = 2;
        if (bad == 4) profile.qos_kind = 3;
        if (bad == 5) profile.qos_word = 1;
        if (bad == 6) { profile.qos_kind = 1; profile.qos_word = 0x10000; }
        assert(rpi5_pcie_qos_init(&empty, &m.ubus, &profile, owner) == RPI5_PCIE_QOS_ARGUMENT);
        assert(!memcmp(&empty, &before, sizeof empty) && !m.calls);
    }
    assert(rpi5_pcie_qos_init(0, &m.ubus, &m.s.profile, owner) == RPI5_PCIE_QOS_ARGUMENT);
    assert(rpi5_pcie_qos_init(&empty, &m.ubus, 0, owner) == RPI5_PCIE_QOS_ARGUMENT);
    assert(rpi5_pcie_qos_init(&empty, &m.ubus, &m.s.profile, 0) == RPI5_PCIE_QOS_ARGUMENT);
    printf("PCIE_QOS_HOST_PASS CALLBACK_FAILURES=%u DEPENDENCY_FAILURES=%u NO_MMIO=1\n", failures, failures);
    return 0;
}
