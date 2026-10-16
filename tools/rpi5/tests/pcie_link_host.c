/* SPDX-License-Identifier: BSD-2-Clause */
/* Model only: prerequisite states are not actual controller admission. */
#include "pcie_link.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum kind { CHECK, R32, W32, ORDER, R16, W16, NOW, DELAY };
struct event { enum kind kind; uint32_t offset; };
struct model {
    struct rpi5_pcie_link *session;
    unsigned calls, fail_at, bad_at, wrong_at, clock_at, drop_at;
    unsigned delay_at, delay_mode, poll_reads, up_at, released_checks;
    uint64_t clock, returned_time;
    uint32_t ctrl, capability, debug, misc, class_code, endian, phy;
    uint16_t ctl2, link_control, negotiated;
    uint32_t initial_status, final_status;
    struct event events[180];
};
struct fixture {
    struct model m;
    struct rpi5_pcie_link link;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_windows windows;
    struct rpi5_pcie_rc rc;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_link_io io;
};
static int step(struct model *m, enum kind kind, uint32_t offset)
{
    assert(m->session->state == RPI5_PCIE_LINK_BUSY);
    assert(m->calls < sizeof m->events/sizeof m->events[0]);
    m->events[m->calls++] = (struct event){kind,offset};
    struct rpi5_pcie_link_observation out;
    assert(rpi5_pcie_link_train(m->session,&out) == RPI5_PCIE_LINK_STATE);
    return m->calls == m->fail_at;
}
static int check(void *context, unsigned released)
{
    struct model *m = context;
    int rc = step(m,CHECK,released);
    assert(released == !!(m->ctrl & 4));
    if (released) m->released_checks++;
    return rc ? -1 : 0;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    if (step(m,R32,offset)) return -1;
    switch (offset) {
        case 0x4068:
            if (!(m->ctrl & 4)) *value = m->initial_status;
            else if (m->released_checks == 2) *value = m->final_status;
            else { m->poll_reads++; *value = m->poll_reads >= m->up_at ? 0xb0 : 0x90; }
            break;
        case 0x4064: *value = m->ctrl; break;
        case 0x04dc: *value = m->capability; break;
        case 0x4304: *value = m->debug; break;
        case 0x4008: *value = m->misc; break;
        case 0x043c: *value = m->class_code; break;
        case 0x0188: *value = m->endian; break;
        case 0x184c: *value = m->phy; break;
        default: assert(0); /* No config selector, endpoint, IRQ or DMA accesses. */
    }
    if (m->calls == m->bad_at) *value = UINT32_MAX;
    if (m->calls == m->wrong_at) *value ^= offset == 0x4068 ? 0x80 : 4;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m = context;
    int failed = step(m,W32,offset);
    switch (offset) {
        case 0x04dc:
            assert(!(m->ctrl & 4) && value == ((m->capability & ~0xfu) | 2));
            if (m->calls != m->drop_at) m->capability = value;
            break;
        case 0x4304:
            assert(!(m->ctrl & 4) && value == (m->debug & ~0x310002u));
            if (m->calls != m->drop_at) m->debug = value;
            break;
        case 0x4064:
            assert(!(m->ctrl & 4) && value == (m->ctrl | 4));
            assert((m->capability & 0x1ff) == 0x42 && (m->ctl2 & 0xf) == 2);
            assert(!(m->debug & 0x831000a));
            if (m->calls != m->drop_at) m->ctrl = value;
            break;
        default: assert(0);
    }
    return failed ? -1 : 0; /* A failed write may already have taken effect. */
}
static int order(void *context) { return step(context,ORDER,0) ? -1 : 0; }
static int read16(void *context, uint32_t offset, uint16_t *value)
{
    struct model *m = context;
    if (step(m,R16,offset)) return -1;
    assert(offset == 0xbc || offset == 0xdc || offset == 0xbe);
    *value = offset == 0xbc ? m->link_control : offset == 0xdc ? m->ctl2 : m->negotiated;
    if (m->calls == m->bad_at) *value = UINT16_MAX;
    if (m->calls == m->wrong_at) *value ^= 1;
    return 0;
}
static int write16(void *context, uint32_t offset, uint16_t value)
{
    struct model *m = context;
    int failed = step(m,W16,offset);
    assert(offset == 0xdc && !(m->ctrl & 4) && value == ((m->ctl2 & ~0xfu) | 2));
    if (m->calls != m->drop_at) m->ctl2 = value;
    return failed ? -1 : 0;
}
static int now_us(void *context, uint64_t *value)
{
    struct model *m = context;
    if (step(m,NOW,0)) return -1;
    *value = m->calls == m->clock_at ? m->returned_time-1 : m->clock;
    m->returned_time = *value;
    return 0;
}
static int delay_us(void *context, uint32_t delay)
{
    struct model *m = context;
    if (step(m,DELAY,delay)) return -1;
    assert(m->ctrl & 4);
    assert(delay == 100000 || delay == 5000);
    uint64_t advance = delay;
    if (m->calls == m->delay_at) {
        if (m->delay_mode == 1) advance = 0;
        if (m->delay_mode == 2) advance--;
        if (m->delay_mode == 3) advance += 11001;
        if (m->delay_mode == 4) advance += 10000;
        if (m->delay_mode == 5) advance = UINT64_MAX-m->clock+1; /* Wrap to zero. */
    }
    m->clock += advance;
    return 0;
}
static void prepare(struct fixture *f, unsigned up_at)
{
    memset(f,0,sizeof *f);
    f->m.session = &f->link;
    f->m.up_at = up_at;
    f->m.clock = 1000000;
    f->m.ctrl = 0x10203000;
    f->m.capability = 0xa5000043;
    f->m.debug = 0x40310002;
    f->m.ctl2 = 0xb5a3;
    f->m.link_control = 0x40;
    f->m.negotiated = 0x42;
    f->m.initial_status = 0x80;
    f->m.final_status = 0xb0;
    f->m.misc = 0x81203480;
    f->m.class_code = 0xab060400;
    f->m.endian = 0xa0000001;
    f->m.phy = 0x80000012;
    f->reset.state = RPI5_PCIE_RESET_COMPLETE;
    f->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    f->serdes.bridge_reset = &f->reset;
    f->serdes.calibration = &f->rescal;
    f->serdes.state = RPI5_PCIE_SERDES_COMPLETE;
    f->serdes.mdio.state = RPI5_PCIE_MDIO_READY;
    f->serdes.mdio.io = (struct rpi5_pcie_mdio_io){&f->m,0x1000120000,0x9310,
        read32,write32,order,now_us,delay_us};
    f->windows.io = (struct rpi5_pcie_windows_io){&f->m,0x1000120000,0x9310,
        0,read32,write32,order};
    f->windows.state = RPI5_PCIE_WINDOWS_COMPLETE;
    f->ubus.serdes = &f->serdes;
    f->ubus.state = RPI5_PCIE_UBUS_COMPLETE;
    f->rc.state = RPI5_PCIE_RC_COMPLETE;
    f->rc.windows = &f->windows;
    f->rc.bridge_reset = &f->reset; f->rc.calibration = &f->rescal;
    f->rc.io = (struct rpi5_pcie_rc_io){read16,write16};
    f->io = (struct rpi5_pcie_link_io){check,read16,write16,&f->rc};
    assert(!rpi5_pcie_link_init(&f->link,&f->ubus,&f->windows,&f->io));
    assert(!f->m.calls && f->link.state == RPI5_PCIE_LINK_READY);
}
static void reject(struct fixture *f, int rc)
{
    struct rpi5_pcie_link_observation out, before;
    memset(&out,0xa5,sizeof out); before = out;
    int actual = rpi5_pcie_link_train(&f->link,&out);
    if (actual != rc) fprintf(stderr,"reject got=%d want=%d calls=%u fail=%u bad=%u wrong=%u clock=%u delay=%u/%u drop=%u up=%u\n",
        actual,rc,f->m.calls,f->m.fail_at,f->m.bad_at,f->m.wrong_at,f->m.clock_at,
        f->m.delay_at,f->m.delay_mode,f->m.drop_at,f->m.up_at);
    assert(actual == rc);
    assert(!memcmp(&out,&before,sizeof out));
    assert(f->link.state == RPI5_PCIE_LINK_QUARANTINED);
    assert(f->windows.state == RPI5_PCIE_WINDOWS_QUARANTINED);
    assert(f->rc.state == RPI5_PCIE_RC_QUARANTINED);
    assert(f->ubus.state == RPI5_PCIE_UBUS_QUARANTINED);
    assert(f->serdes.state == RPI5_PCIE_SERDES_QUARANTINED);
    assert(f->serdes.mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    assert(f->reset.state == RPI5_PCIE_RESET_COMPLETE);
    assert(f->rescal.state == RPI5_PCIE_RESCAL_COMPLETE);
    unsigned calls = f->m.calls;
    assert(rpi5_pcie_link_train(&f->link,&out) == RPI5_PCIE_LINK_STATE);
    assert(rpi5_pcie_link_init(&f->link,&f->ubus,&f->windows,&f->io) == RPI5_PCIE_LINK_STATE);
    assert(f->m.calls == calls);
}
int main(void)
{
    struct fixture f;
    struct rpi5_pcie_link_observation out;
    unsigned injected = 0;
    for (unsigned poll = 1; poll <= 21; poll++) {
        prepare(&f,poll);
        assert(!rpi5_pcie_link_train(&f.link,&out));
        assert(out.poll_reads == poll && out.poll_elapsed_us == (poll-1)*5000);
        assert(out.reset_wait_us == 100000 && out.generation == 2 && out.lanes == 4);
        assert(out.status_before == 0x80 && out.status_up == 0xb0 && out.status_final == 0xb0);
        assert(out.control_before == 0x10203000 && out.control_released == 0x10203004);
        assert(out.capability_before == 0xa5000043 && out.capability_after == 0xa5000042);
        assert(out.control2_before == 0xb5a3 && out.control2_after == 0xb5a2);
        assert(out.debug_before == 0x40310002 && out.debug_after == 0x40000000);
        assert(f.link.state == RPI5_PCIE_LINK_COMPLETE && f.link.completed_callbacks == f.m.calls);
        unsigned total = f.m.calls;
        assert(total == 41+4*(poll-1) && total <= 121);
        assert(rpi5_pcie_link_train(&f.link,&out) == RPI5_PCIE_LINK_STATE);
        assert(rpi5_pcie_link_init(&f.link,&f.ubus,&f.windows,&f.io) == RPI5_PCIE_LINK_STATE);
        assert(f.m.calls == total);
        struct event events[180]; memcpy(events,f.m.events,sizeof events);
        assert(events[total-1].kind == R32 && events[total-1].offset == 0x4068);
        for (unsigned at = 1; at <= total; at++) {
            prepare(&f,poll); f.m.fail_at = at;
            reject(&f,RPI5_PCIE_LINK_IO);
            assert(f.m.calls == at && f.link.completed_callbacks == at-1);
            assert(!memcmp(events,f.m.events,at*sizeof events[0]));
            injected++;
            if (events[at-1].kind == R32 || events[at-1].kind == R16) {
                prepare(&f,poll); f.m.bad_at = at;
                reject(&f,RPI5_PCIE_LINK_READBACK); assert(f.m.calls == at);
            }
            if (events[at-1].kind == W32 || events[at-1].kind == W16) {
                prepare(&f,poll); f.m.drop_at = at;
                reject(&f,RPI5_PCIE_LINK_READBACK); assert(f.m.calls == at+2);
            }
            if (events[at-1].kind == NOW && at > 27) {
                prepare(&f,poll); f.m.clock_at = at;
                reject(&f,RPI5_PCIE_LINK_CLOCK); assert(f.m.calls == at);
            }
        }
    }
    /* Downtrained links remain explicit observations, not a bandwidth claim. */
    const unsigned lanes[] = {1,2,4};
    for (unsigned gen = 1; gen <= 2; gen++) for (unsigned i = 0; i < 3; i++) {
        prepare(&f,2); f.m.negotiated = gen | (lanes[i] << 4);
        assert(!rpi5_pcie_link_train(&f.link,&out));
        assert(out.generation == gen && out.lanes == lanes[i]);
    }
    /* Finite poll cap, even when PHY is up but data link never becomes active. */
    prepare(&f,22); reject(&f,RPI5_PCIE_LINK_TIMEOUT);
    assert(f.m.poll_reads == 21 && f.m.clock == 1200000);
    prepare(&f,21); assert(!rpi5_pcie_link_train(&f.link,&out));
    unsigned total = f.m.calls;
    struct event events[180]; memcpy(events,f.m.events,sizeof events);
    for (unsigned at = 1; at <= total; at++) {
        if (events[at-1].kind == DELAY) {
            for (unsigned mode = 1; mode <= 5; mode++) {
                prepare(&f,21); f.m.delay_at = at; f.m.delay_mode = mode;
                if (mode == 4 && events[at-1].offset == 100000) {
                    assert(!rpi5_pcie_link_train(&f.link,&out)); assert(out.reset_wait_us == 110000);
                } else {
                    reject(&f, mode == 3 || mode == 4 ? RPI5_PCIE_LINK_TIMEOUT : RPI5_PCIE_LINK_CLOCK);
                }
            }
        }
    }
    /* Bad quiescence and configuration must never release PERST#. */
    const uint32_t initial[] = {0,0x10,0x20,0xb0,0xc0};
    for (unsigned i = 0; i < sizeof initial/sizeof initial[0]; i++) {
        prepare(&f,1); f.m.initial_status = initial[i];
        reject(&f,RPI5_PCIE_LINK_NOT_QUIESCENT); assert(f.m.calls == 2 && !(f.m.ctrl & 4));
    }
    prepare(&f,1); f.m.ctrl |= 1; reject(&f,RPI5_PCIE_LINK_NOT_QUIESCENT);
    prepare(&f,1); f.m.misc &= ~0x1000u; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.misc ^= 0x100000u; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.class_code ^= 1; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.endian |= 4; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.phy ^= 1; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.link_control |= 1; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.link_control |= 0x100; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.capability ^= 0x60; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.debug |= 0x08000000; reject(&f,RPI5_PCIE_LINK_PROFILE);
    prepare(&f,1); f.m.debug |= 8; reject(&f,RPI5_PCIE_LINK_PROFILE);
    const uint16_t invalid[] = {0x40,0x43,0x02,0x32,0x82,0x842};
    for (unsigned i = 0; i < sizeof invalid/sizeof invalid[0]; i++) {
        prepare(&f,1); f.m.negotiated = invalid[i]; reject(&f,RPI5_PCIE_LINK_PROFILE);
    }
    const uint32_t loss[] = {0,0x80,0x90,0xa0,0xf0};
    for (unsigned i = 0; i < sizeof loss/sizeof loss[0]; i++) {
        prepare(&f,1); f.m.final_status = loss[i]; reject(&f,RPI5_PCIE_LINK_LOST);
    }
    /* Final pass rejects changed control, target speed, debug and ASPM. */
    prepare(&f,1); assert(!rpi5_pcie_link_train(&f.link,&out));
    total = f.m.calls; memcpy(events,f.m.events,sizeof events);
    for (unsigned at = total-7; at <= total; at++) {
        if (events[at-1].kind != R32 && events[at-1].kind != R16) continue;
        prepare(&f,1); f.m.wrong_at = at;
        int rc = events[at-1].offset == 0x4068 ? RPI5_PCIE_LINK_LOST :
            (events[at-1].offset == 0xbc || events[at-1].offset == 0xbe) ?
                RPI5_PCIE_LINK_PROFILE : RPI5_PCIE_LINK_READBACK;
        reject(&f,rc); assert(f.m.calls == at);
    }
    prepare(&f,1); f.ubus.state = RPI5_PCIE_UBUS_QUARANTINED;
    reject(&f,RPI5_PCIE_LINK_DEPENDENCY); assert(!f.m.calls);
    /* Pure init rejects wrong owner/mapping, incomplete dependencies/missing IO. */
    for (unsigned mutation = 0; mutation < 18; mutation++) {
        prepare(&f,1); memset(&f.link,0,sizeof f.link);
        if (mutation == 0) f.windows.io.context = 0;
        if (mutation == 1) f.windows.io.physical_base++;
        if (mutation == 2) f.windows.io.mapped_bytes--;
        if (mutation == 3) f.windows.io.read32 = 0;
        if (mutation == 4) f.serdes.mdio.io.now_us = 0;
        if (mutation == 5) f.serdes.state = RPI5_PCIE_SERDES_READY;
        if (mutation == 6) f.reset.state = RPI5_PCIE_RESET_READY;
        if (mutation == 7) f.rescal.state = RPI5_PCIE_RESCAL_READY;
        if (mutation == 8) f.io.read16 = 0;
        if (mutation == 9) f.io.write16 = 0;
        if (mutation == 10) f.io.check_lifecycle = 0;
        if (mutation == 11) f.rc.state = RPI5_PCIE_RC_READY;
        if (mutation == 12) f.rc.windows = 0;
        if (mutation == 13) f.rc.io.read16 = 0;
        if (mutation == 14) f.rc.bridge_reset = 0;
        if (mutation == 15) f.rc.calibration = 0;
        if (mutation == 16) f.io.rc = 0;
        if (mutation == 17) f.rc.io.write16 = 0;
        assert(rpi5_pcie_link_init(&f.link,&f.ubus,&f.windows,&f.io) ==
            (mutation >= 8 && mutation <= 10 ? RPI5_PCIE_LINK_ARGUMENT : RPI5_PCIE_LINK_DEPENDENCY));
        assert(!f.m.calls && f.link.state == RPI5_PCIE_LINK_EMPTY);
    }
    assert(injected == 1701);
    printf("PCIE_LINK_HOST_PASS FAILURE_POSITIONS=%u\n",injected);
    return 0;
}
