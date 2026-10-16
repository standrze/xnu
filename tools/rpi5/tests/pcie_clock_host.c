/* SPDX-License-Identifier: BSD-2-Clause */
/* Native callback model only; completed prerequisite states are not board proof. */
#include "pcie_clock.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
    struct rpi5_pcie_clock s;
    struct rpi5_pcie_qos qos;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_windows windows;
    struct rpi5_pcie_rc rc;
    struct rpi5_pcie_link link;
    unsigned calls, reads, writes, fail_at, dep_at, bad_read, corrupt_read, change_at, half_reads;
    uint32_t offsets[80], status, control, debug, axi, cap, root, corruption;
    uint16_t half;
    int post;
};
static int step(struct model *m)
{
    assert(m->s.state == RPI5_PCIE_CLOCK_BUSY);
    struct rpi5_pcie_clock_pre_observation pre;
    struct rpi5_pcie_clock_post_observation post;
    assert(rpi5_pcie_clock_prepare(&m->s, &pre) == RPI5_PCIE_CLOCK_STATE);
    assert(rpi5_pcie_clock_finish(&m->s, &m->link, &post) == RPI5_PCIE_CLOCK_STATE);
    m->calls++;
    if (m->calls == m->dep_at) m->reset.state = RPI5_PCIE_RESET_QUARANTINED;
    if (m->calls == m->change_at) m->control ^= 4;
    return m->calls == m->fail_at;
}
static int owner(void *p) { return step(p) ? -1 : 0; }
static int lifecycle(void *p, unsigned released)
{
    struct model *m = p;
    assert(m->post && released == 1);
    return step(m) ? -1 : 0;
}
static uint32_t *reg(struct model *m, uint32_t off)
{
    switch (off) {
        case 0x4068: return &m->status;
        case 0x4064: return &m->control;
        case 0x4304: return &m->debug;
        case 0x416c: return &m->axi;
        case 0x04dc: return &m->cap;
        case 0x04f8: return &m->root;
        default: assert(0); return 0; /* No timer/config/window/IRQ/DMA accesses. */
    }
}
static int read32(void *p, uint32_t off, uint32_t *out)
{
    struct model *m = p;
    if (step(m)) return -1;
    assert(m->reads < 80); m->offsets[m->reads++] = off;
    *out = *reg(m, off);
    if (m->reads == m->bad_read) *out = UINT32_MAX;
    if (m->reads == m->corrupt_read) *out ^= m->corruption;
    return 0;
}
static int read16(void *p, uint32_t off, uint16_t *out)
{
    struct model *m = p;
    assert(m->post && off == 0xbc);
    if (step(m)) return -1;
    m->half_reads++; *out = m->half; return 0;
}
static int write16(void *p, uint32_t off, uint16_t value)
{ (void)p; (void)off; (void)value; assert(0); return -1; }
static int write32(void *p, uint32_t off, uint32_t value)
{
    struct model *m = p;
    int rc = step(m);
    if (!m->post) {
        assert(m->s.profile.aspm_no_l0s && !m->writes && off == 0x04dc);
        assert(value == 0x81000842); /* Only L0s advertisement cleared. */
    } else {
        unsigned mode = m->s.profile.clkreq;
        if (mode == RPI5_PCIE_CLKREQ_ABSENT) mode = RPI5_PCIE_CLKREQ_DEFAULT;
        if (mode != RPI5_PCIE_CLKREQ_DEFAULT && !m->writes) {
            assert(off == 0x04f8 && value == 0xa5a50217); /* mode=2, other fields preserved. */
        } else {
            assert(off == 0x4304);
            const uint32_t bits = mode == RPI5_PCIE_CLKREQ_DEFAULT ? 0x200000 :
                mode == RPI5_PCIE_CLKREQ_SAFE ? 0x110000 : 2;
            assert(value == (0x40008000 | bits));
            if (mode != RPI5_PCIE_CLKREQ_DEFAULT) assert(m->root == 0xa5a50217);
        }
    }
    m->writes++; *reg(m, off) = value;
    return rc ? -1 : 0; /* Failure may follow an effective write. */
}
static int order(void *p) { return step(p) ? -1 : 0; }
static void prepare(struct model *m, unsigned mode, unsigned no_l0s)
{
    memset(m, 0, sizeof *m);
    m->qos.state = RPI5_PCIE_QOS_COMPLETE; m->qos.ubus = &m->ubus; m->qos.check_owner = owner;
    m->qos.profile = (struct rpi5_pcie_profile){2,4,mode,no_l0s,0,0};
    m->ubus.state = RPI5_PCIE_UBUS_COMPLETE; m->ubus.serdes = &m->serdes;
    m->serdes.state = RPI5_PCIE_SERDES_COMPLETE; m->serdes.mdio.state = RPI5_PCIE_MDIO_READY;
    m->reset.state = RPI5_PCIE_RESET_COMPLETE; m->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    m->serdes.bridge_reset = &m->reset; m->serdes.calibration = &m->rescal;
    m->serdes.mdio.io = (struct rpi5_pcie_mdio_io){m,UINT64_C(0x1000120000),0x9310,read32,write32,order,0,0};
    m->status = 0x80; m->debug = 0x40008000; m->axi = 0x3800;
    m->cap = 0x81000c42; m->root = 0xa5a502ff; m->half = 0x200;
    assert(!rpi5_pcie_clock_init(&m->s, &m->qos)); assert(!m->calls);
}
static void post_prepare(struct model *m, unsigned mode, unsigned no_l0s)
{
    prepare(m, mode, no_l0s);
    struct rpi5_pcie_clock_pre_observation pre;
    assert(!rpi5_pcie_clock_prepare(&m->s, &pre));
    m->windows.state = RPI5_PCIE_WINDOWS_COMPLETE;
    m->windows.io = (struct rpi5_pcie_windows_io){m,UINT64_C(0x1000120000),0x9310,owner,read32,write32,order};
    m->rc.state = RPI5_PCIE_RC_COMPLETE; m->rc.windows = &m->windows;
    m->rc.bridge_reset = &m->reset; m->rc.calibration = &m->rescal;
    m->rc.io = (struct rpi5_pcie_rc_io){read16,write16};
    m->link.state = RPI5_PCIE_LINK_COMPLETE; m->link.ubus = &m->ubus; m->link.windows = &m->windows;
    m->link.io = (struct rpi5_pcie_link_io){lifecycle,read16,write16,&m->rc};
    m->post = 1; m->control = 4; m->status = 0xb0;
    m->calls = m->reads = m->writes = 0;
}
static int run(struct model *m)
{
    if (m->post) {
        struct rpi5_pcie_clock_post_observation out, saved;
        memset(&out, 0xa5, sizeof out); saved = out;
        int rc = rpi5_pcie_clock_finish(&m->s, &m->link, &out);
        if (rc) assert(!memcmp(&out, &saved, sizeof out));
        else {
            assert(out.completed_callbacks == m->calls && out.writes == m->writes);
            assert(out.declared_mode == m->s.profile.clkreq && out.final_status == 0xb0);
            assert(out.effective_mode == (m->s.profile.clkreq ? m->s.profile.clkreq : 2));
            assert(m->s.state == RPI5_PCIE_CLOCK_COMPLETE && m->calls <= 160);
        }
        return rc;
    }
    struct rpi5_pcie_clock_pre_observation out, saved;
    memset(&out, 0xa5, sizeof out); saved = out;
    int rc = rpi5_pcie_clock_prepare(&m->s, &out);
    if (rc) assert(!memcmp(&out, &saved, sizeof out));
    else {
        assert(out.completed_callbacks == m->calls && out.writes == m->writes);
        assert(out.capability_before == 0x81000c42 && out.capability_after == m->cap);
        assert(m->s.state == RPI5_PCIE_CLOCK_PREPARED && m->calls <= 61);
    }
    return rc;
}
static void rejected(struct model *m, int rc)
{
    assert(run(m) == rc);
    assert(m->s.state == RPI5_PCIE_CLOCK_QUARANTINED);
    assert(m->qos.state == RPI5_PCIE_QOS_QUARANTINED && m->ubus.state == RPI5_PCIE_UBUS_QUARANTINED);
    assert(m->serdes.state == RPI5_PCIE_SERDES_QUARANTINED && m->serdes.mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    if (m->post) assert(m->link.state == RPI5_PCIE_LINK_QUARANTINED &&
        m->windows.state == RPI5_PCIE_WINDOWS_QUARANTINED && m->rc.state == RPI5_PCIE_RC_QUARANTINED);
    unsigned calls = m->calls, writes = m->writes;
    assert(run(m) == RPI5_PCIE_CLOCK_STATE);
    assert(rpi5_pcie_clock_init(&m->s, &m->qos) == RPI5_PCIE_CLOCK_STATE);
    assert(calls == m->calls && writes == m->writes);
}
int main(void)
{
    struct model m;
    unsigned failures = 0, read_failures = 0;
    for (unsigned mode = 0; mode < 4; mode++) for (unsigned no_l0s = 0; no_l0s < 2; no_l0s++)
    for (unsigned post = 0; post < 2; post++) {
        void (*setup)(struct model *, unsigned, unsigned) = post ? post_prepare : prepare;
        setup(&m, mode, no_l0s); assert(!run(&m));
        unsigned calls = m.calls, reads = m.reads;
        uint32_t offsets[80]; memcpy(offsets, m.offsets, sizeof offsets);
        assert(m.writes == (post ? (mode == 0 || mode == 2 ? 1u : 2u) : no_l0s));
        for (unsigned fail = 1; fail <= calls; fail++) {
            setup(&m, mode, no_l0s); m.fail_at = fail;
            /* A lifecycle callback failure has a more specific code. */
            int rc = run(&m);
            assert(rc == RPI5_PCIE_CLOCK_IO || rc == RPI5_PCIE_CLOCK_LIFECYCLE);
            assert(m.calls == fail && m.s.completed_callbacks == fail-1);
            assert(m.s.state == RPI5_PCIE_CLOCK_QUARANTINED);
            unsigned after = m.calls; assert(run(&m) == RPI5_PCIE_CLOCK_STATE && after == m.calls);
            failures++;
            setup(&m, mode, no_l0s); m.dep_at = fail;
            rejected(&m, RPI5_PCIE_CLOCK_DEPENDENCY); assert(m.calls == fail);
        }
        for (unsigned read = 1; read <= reads; read++) {
            setup(&m, mode, no_l0s); m.bad_read = read;
            rejected(&m, RPI5_PCIE_CLOCK_READBACK); read_failures++;
            /* Wrong target fields at both immediate and final verification. */
            if ((offsets[read-1] == 0x04f8 || offsets[read-1] == 0x4304 || offsets[read-1] == 0x04dc) &&
                read > (post ? 7u : 5u)) {
                setup(&m, mode, no_l0s); m.corrupt_read = read;
                m.corruption = offsets[read-1] == 0x04dc ? 0x400 :
                    offsets[read-1] == 0x4304 ? 0x08000000 : 0x10;
                int rc = run(&m);
                assert(rc == RPI5_PCIE_CLOCK_READBACK || rc == RPI5_PCIE_CLOCK_PROFILE ||
                    rc == RPI5_PCIE_CLOCK_LIFECYCLE);
                assert(m.s.state == RPI5_PCIE_CLOCK_QUARANTINED);
            }
        }
    }
    for (unsigned post = 0; post < 2; post++) for (unsigned fault = 0; fault < 9; fault++) {
        (post ? post_prepare : prepare)(&m, 1, 1);
        if (fault == 0) m.status ^= 0x10;
        if (fault == 1) m.control ^= 4;
        if (fault == 2) m.control |= 1;
        if (fault == 3) m.status |= 0x40;
        if (fault == 4) m.debug |= 0x08000000;
        if (fault == 5) m.debug |= 8;
        if (fault == 6) m.axi &= ~0x2000u;
        if (fault == 7) m.axi |= 0x80;
        if (fault == 8) m.status &= ~0x80u;
        rejected(&m, RPI5_PCIE_CLOCK_LIFECYCLE); assert(!m.writes);
    }
    const uint16_t halves[] = {1,2,0x100,0x10,0x20,UINT16_MAX};
    for (unsigned i = 0; i < sizeof halves/sizeof halves[0]; i++) {
        post_prepare(&m, 1, 1); m.half |= halves[i];
        rejected(&m, RPI5_PCIE_CLOCK_PROFILE); assert(!m.writes);
    }
    post_prepare(&m, 0, 1); m.debug |= 2; rejected(&m, RPI5_PCIE_CLOCK_PROFILE); assert(!m.writes);
    post_prepare(&m, 0, 1); m.cap |= 0x400; rejected(&m, RPI5_PCIE_CLOCK_PROFILE); assert(!m.writes);
    prepare(&m, 1, 1); m.cap ^= 0x10; rejected(&m, RPI5_PCIE_CLOCK_PROFILE); assert(!m.writes);
    /* No callback or mutation for an unbound wrong-owner link/dependency. */
    for (unsigned bad = 0; bad < 12; bad++) {
        post_prepare(&m, 2, 1);
        if (bad == 0) m.link.ubus = 0;
        if (bad == 1) m.link.state = RPI5_PCIE_LINK_READY;
        if (bad == 2) m.windows.state = RPI5_PCIE_WINDOWS_READY;
        if (bad == 3) m.rc.state = RPI5_PCIE_RC_READY;
        if (bad == 4) m.rc.bridge_reset = 0;
        if (bad == 5) m.rc.calibration = 0;
        if (bad == 6) m.windows.io.context = 0;
        if (bad == 7) m.windows.io.mapped_bytes--;
        if (bad == 8) m.windows.io.read32 = 0;
        if (bad == 9) m.link.io.read16 = 0;
        if (bad == 10) m.link.io.write16 = 0;
        if (bad == 11) m.link.io.check_lifecycle = 0;
        assert(run(&m) == RPI5_PCIE_CLOCK_DEPENDENCY && !m.calls && !m.writes);
        assert(m.s.state == RPI5_PCIE_CLOCK_PREPARED && !m.s.link);
    }
    prepare(&m, 1, 1);
    struct rpi5_pcie_clock empty = {0}, saved = empty;
    m.qos.profile.clkreq = 4;
    assert(rpi5_pcie_clock_init(&empty, &m.qos) == RPI5_PCIE_CLOCK_PROFILE);
    assert(!memcmp(&empty, &saved, sizeof empty) && !m.calls);
    assert(rpi5_pcie_clock_init(0, &m.qos) == RPI5_PCIE_CLOCK_ARGUMENT);
    assert(rpi5_pcie_clock_prepare(&m.s, 0) == RPI5_PCIE_CLOCK_ARGUMENT);
    assert(rpi5_pcie_clock_finish(&m.s, 0, 0) == RPI5_PCIE_CLOCK_ARGUMENT);
    printf("PCIE_CLOCK_HOST_PASS CALLBACK_FAILURES=%u DEPENDENCY_FAILURES=%u READ_FAILURES=%u NO_MMIO=1\n",
        failures, failures, read_failures);
    return 0;
}
