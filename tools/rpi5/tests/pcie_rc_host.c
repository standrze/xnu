/* SPDX-License-Identifier: BSD-2-Clause */
/* Callback model, not physical PCIe evidence. Shared reset/calibration/SerDes
 * admission is synthetic. RC, windows, UBUS and link functions are REAL cores. */
#include "pcie_link.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum kind { CHECK, READ32, WRITE32, ORDER, READ16, WRITE16, NOW, DELAY };
struct event { enum kind kind; uint32_t offset; };
struct fixture {
    struct rpi5_pcie_rc rc;
    struct rpi5_pcie_windows windows;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_link link;
    struct rpi5_pcie_fdt fdt;
    uint32_t regs[0x4400/4];
    struct event events[400];
    unsigned calls, fail_at, bad_at, drop_at, drift_at, corrupt_at;
    unsigned fallback, timed, link_phase, released_checks;
    uint64_t clock;
};
static int step(struct fixture *f, enum kind kind, uint32_t offset)
{
    assert(f->calls < sizeof f->events/sizeof f->events[0]);
    f->events[f->calls++] = (struct event){kind,offset};
    if (f->rc.state == RPI5_PCIE_RC_BUSY) {
        struct rpi5_pcie_rc_observation out;
        assert(rpi5_pcie_rc_configure(&f->rc,&out) == RPI5_PCIE_RC_STATE);
    }
    if (f->calls == f->drift_at) f->regs[0x4008/4] ^= 1;
    return f->calls == f->fail_at;
}
static int check(void *context) { return step(context,CHECK,0) ? -1 : 0; }
static int check_link(void *context, unsigned released)
{
    struct fixture *f = context;
    assert(released == !!(f->regs[0x4064/4] & 4));
    if (released) f->released_checks++;
    return step(f,CHECK,released) ? -1 : 0;
}
static int window_reg(uint32_t offset)
{
    for (unsigned i = 0; i < 3; i++)
        if (offset == 0x402c+8*i || offset == 0x4030+8*i ||
            offset == 0x40ac+8*i || offset == 0x40b0+8*i) return 1;
    for (unsigned i = 0; i < 2; i++)
        if (offset == 0x400c+8*i || offset == 0x4010+8*i ||
            offset == 0x4070+4*i || offset == 0x4080+8*i || offset == 0x4084+8*i) return 1;
    return 0;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct fixture *f = context;
    assert(!(offset & 3) && offset < sizeof f->regs);
    assert(window_reg(offset) || offset == 0x4068 || offset == 0x4064 ||
        offset == 0x4008 || offset == 0x04dc || offset == 0x043c || offset == 0x0188 ||
        offset == 0x40a4 || offset == 0x40a8 || offset == 0x405c || offset == 0x416c ||
        offset == 0x40a0 || offset == 0x184c || offset == 0x4304);
    if (step(f,READ32,offset)) return -1;
    *value = f->regs[offset/4];
    if (f->link_phase && offset == 0x4068 && (f->regs[0x4064/4] & 4)) *value = 0xb0;
    if (f->calls == f->bad_at) *value = UINT32_MAX;
    if (f->calls == f->corrupt_at) *value ^= offset == 0x4068 ? 0x80 : offset == 0x4064 ? 4 : 1;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct fixture *f = context;
    assert(window_reg(offset) || offset == 0x4008 || offset == 0x043c || offset == 0x0188 ||
        (f->timed && (offset == 0x40a4 || offset == 0x4170 || offset == 0x40a8 ||
            offset == 0x405c || offset == 0x416c || offset == 0x40a0)) ||
        (f->link_phase && (offset == 0x04dc || offset == 0x4304 || offset == 0x4064)));
    /* No configuration selector/endpoint, unused windows, MSI or DMA access. */
    if (!f->link_phase) assert(!(f->regs[0x4064/4] & 4));
    int failed = step(f,WRITE32,offset);
    if (f->calls != f->drop_at) f->regs[offset/4] = value;
    if (offset == 0x416c && f->fallback) f->regs[offset/4] &= ~0x1000u;
    return failed ? -1 : 0; /* Failure can follow a completed physical write. */
}
static int order(void *context)
{
    struct fixture *f = context;
    assert(f->calls && (f->events[f->calls-1].kind == WRITE32 ||
        f->events[f->calls-1].kind == WRITE16));
    return step(f,ORDER,0) ? -1 : 0;
}
static int read16(void *context, uint32_t offset, uint16_t *value)
{
    struct fixture *f = context;
    assert(offset == 0xbc || (f->link_phase && (offset == 0xdc || offset == 0xbe)));
    if (step(f,READ16,offset)) return -1;
    *value = f->regs[(offset & ~3u)/4] >> ((offset & 2)*8);
    if (f->calls == f->bad_at) *value = UINT16_MAX;
    if (f->calls == f->corrupt_at) *value ^= 1;
    return 0;
}
static int write16(void *context, uint32_t offset, uint16_t value)
{
    struct fixture *f = context;
    assert(offset == 0xbc || (f->link_phase && offset == 0xdc));
    assert(!(f->regs[0x4064/4] & 4));
    int failed = step(f,WRITE16,offset);
    /* Model the neighboring status halfword independently; a word callback
     * would violate the write allowlist and cannot accidentally pass here. */
    if (f->calls != f->drop_at)
        f->regs[offset/4] = (f->regs[offset/4] & 0xffff0000u) | value;
    return failed ? -1 : 0;
}
static int now_us(void *context, uint64_t *value)
{
    struct fixture *f = context;
    if (step(f,NOW,0)) return -1;
    *value = f->clock;
    return 0;
}
static int delay_us(void *context, uint32_t delay)
{
    struct fixture *f = context;
    if (step(f,DELAY,delay)) return -1;
    f->clock += delay;
    return 0;
}
static void prepare(struct fixture *f)
{
    memset(f,0,sizeof *f);
    for (unsigned i = 0; i < sizeof f->regs/sizeof f->regs[0]; i++) f->regs[i] = 0x12345678;
    f->fdt.bridge_regs = (struct rpi5_range){0x1000120000,0x1000129310};
    f->fdt.mip_regs = (struct rpi5_range){0x1000130000,0x10001300c0};
    f->fdt.mip_target = (struct rpi5_range){0xfffffff000,0x10000000000};
    f->fdt.outbound_count = 2; f->fdt.dma_count = 3;
    f->fdt.outbound[0] = (struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0xfffffffc};
    f->fdt.outbound[1] = (struct rpi5_pcie_window){0x43000000,0x400000000,0x1c00000000,0x300000000};
    f->fdt.dma[0] = (struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0x400000};
    f->fdt.dma[1] = (struct rpi5_pcie_window){0x43000000,0x1000000000,0,0x1000000000};
    f->fdt.dma[2] = (struct rpi5_pcie_window){0x03000000,0xfffffff000,0x1000130000,0x1000};
    struct rpi5_pcie_windows_io io = {f,0x1000120000,0x9310,check,read32,write32,order};
    assert(!rpi5_pcie_windows_init(&f->windows,&f->fdt,&io,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES));
    f->reset.state = RPI5_PCIE_RESET_COMPLETE;
    f->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    struct rpi5_pcie_rc_io half_io = {read16,write16};
    assert(!rpi5_pcie_rc_init(&f->rc,&f->windows,&f->reset,&f->rescal,&half_io));
    f->regs[0x4068/4] = 0x10080; f->regs[0x4064/4] = 0x10203000;
    f->regs[0x4008/4] = 0x91000215; /* Preserve unrelated/SCB-size fields. */
    f->regs[0x04dc/4] = 0xa5000c43;
    f->regs[0x043c/4] = 0xabffffff;
    f->regs[0x0188/4] = 0xa000000d;
    f->regs[0xbc/4] = 0x30420543; /* Independent status halfword, PM + ASPM enabled. */
    f->regs[0xdc/4] = 0x1234b5a3;
    f->regs[0x184c/4] = 0x80000012;
    f->regs[0x4304/4] = 0x40310002;
    f->clock = 1000000;
    assert(!f->calls);
}
static int rejected(struct fixture *f)
{
    struct rpi5_pcie_rc_observation out,before;
    memset(&out,0xa5,sizeof out); before = out;
    int rc = rpi5_pcie_rc_configure(&f->rc,&out);
    if (!rc) fprintf(stderr,"unexpected success calls=%u fail=%u bad=%u drop=%u drift=%u corrupt=%u\n",
        f->calls,f->fail_at,f->bad_at,f->drop_at,f->drift_at,f->corrupt_at);
    assert(rc && !memcmp(&out,&before,sizeof out));
    assert(f->rc.state == RPI5_PCIE_RC_QUARANTINED);
    assert(f->windows.state == RPI5_PCIE_WINDOWS_QUARANTINED);
    assert(f->reset.state == RPI5_PCIE_RESET_COMPLETE);
    assert(f->rescal.state == RPI5_PCIE_RESCAL_COMPLETE);
    unsigned calls = f->calls;
    assert(rpi5_pcie_rc_configure(&f->rc,&out) == RPI5_PCIE_RC_STATE);
    struct rpi5_pcie_rc_io io = {read16,write16};
    assert(rpi5_pcie_rc_init(&f->rc,&f->windows,&f->reset,&f->rescal,&io) == RPI5_PCIE_RC_STATE);
    assert(f->calls == calls);
    return rc;
}
static void rc_tests(void)
{
    struct fixture f;
    struct rpi5_pcie_rc_observation out;
    prepare(&f);
    assert(!rpi5_pcie_rc_configure(&f.rc,&out));
    assert(f.calls == 146 && out.completed_callbacks == 34 && out.window_callbacks == 112);
    assert(out.misc_before == 0x91000215 && out.misc_after == 0x91203695);
    assert(out.class_before == 0xabffffff && out.class_after == 0xab060400);
    assert(out.endian_before == 0xa000000d && out.endian_after == 0xa0000001);
    assert(out.link_control_before == 0x543 && out.link_control_after == 0x440);
    assert(f.regs[0xbc/4] == 0x30420440 && out.capability == 0xa5000c43);
    assert(out.final_status == 0x10080 && out.final_control == 0x10203000);
    assert(f.rc.state == RPI5_PCIE_RC_COMPLETE && f.windows.state == RPI5_PCIE_WINDOWS_COMPLETE);
    struct event events[400]; memcpy(events,f.events,sizeof events);
    assert(events[145].kind == READ32 && events[145].offset == 0x4064);
    unsigned first_window_write = 0, class_write = 0;
    for (unsigned i = 0; i < 146; i++) {
        if (!first_window_write && events[i].kind == WRITE32 && window_reg(events[i].offset)) first_window_write = i;
        if (events[i].kind == WRITE32 && events[i].offset == 0x043c) class_write = i;
    }
    assert(first_window_write > 7 && class_write > 122);
    assert(rpi5_pcie_rc_configure(&f.rc,&out) == RPI5_PCIE_RC_STATE && f.calls == 146);
    for (unsigned at = 1; at <= 146; at++) {
        prepare(&f); f.fail_at = at; rejected(&f);
        assert(f.calls == at && !memcmp(events,f.events,at*sizeof events[0]));
        if (events[at-1].kind == READ32 || events[at-1].kind == READ16) {
            prepare(&f); f.bad_at = at; rejected(&f); assert(f.calls == at);
        }
        if (events[at-1].kind == WRITE32 || events[at-1].kind == WRITE16) {
            prepare(&f); f.drop_at = at; rejected(&f); assert(f.calls == at+2);
        }
    }
    /* Alias/drift after immediate readback must still fail the final pass. */
    prepare(&f); f.drift_at = 135;
    assert(rejected(&f) == RPI5_PCIE_RC_READBACK);
    for (unsigned at = 139; at <= 146; at++) {
        if (events[at-1].kind != READ32 && events[at-1].kind != READ16) continue;
        prepare(&f); f.corrupt_at = at; rejected(&f); assert(f.calls == at);
    }
    const unsigned status[] = {0,0x10,0x20,0xb0,0xc0};
    for (unsigned i = 0; i < sizeof status/sizeof status[0]; i++) {
        prepare(&f); f.regs[0x4068/4] = status[i];
        assert(rejected(&f) == RPI5_PCIE_RC_NOT_QUIESCENT && f.calls == 2);
    }
    prepare(&f); f.regs[0x4064/4] |= 4; assert(rejected(&f) == RPI5_PCIE_RC_NOT_QUIESCENT);
    prepare(&f); f.regs[0x4064/4] |= 1; assert(rejected(&f) == RPI5_PCIE_RC_NOT_QUIESCENT);
    prepare(&f); f.regs[0x04dc/4] ^= 0x60; assert(rejected(&f) == RPI5_PCIE_RC_PROFILE && f.calls == 4);
    for (unsigned bit = 0x10; bit <= 0x20; bit *= 2) {
        prepare(&f); f.regs[0xbc/4] |= bit; assert(rejected(&f) == RPI5_PCIE_RC_PROFILE);
    }
    /* Consumed window state / invalid callbacks / incomplete shared states:
     * pure init refuses without any callback or partially initialized state. */
    for (unsigned mutation = 0; mutation < 11; mutation++) {
        prepare(&f); memset(&f.rc,0,sizeof f.rc);
        struct rpi5_pcie_rc_io io = {read16,write16};
        if (mutation == 0) f.windows.state = RPI5_PCIE_WINDOWS_COMPLETE;
        if (mutation == 1) f.windows.io.context = 0; /* Null context alone is allowed. */
        if (mutation == 2) f.windows.io.physical_base++;
        if (mutation == 3) f.windows.io.mapped_bytes--;
        if (mutation == 4) f.windows.io.check_quiescent = 0;
        if (mutation == 5) f.windows.io.read32 = 0;
        if (mutation == 6) f.windows.io.write32 = 0;
        if (mutation == 7) f.windows.io.order = 0;
        if (mutation == 8) f.reset.state = RPI5_PCIE_RESET_READY;
        if (mutation == 9) f.rescal.state = RPI5_PCIE_RESCAL_READY;
        if (mutation == 10) io.read16 = 0;
        int rc = rpi5_pcie_rc_init(&f.rc,&f.windows,&f.reset,&f.rescal,&io);
        assert(rc == (mutation == 1 ? 0 : mutation == 10 ? RPI5_PCIE_RC_ARGUMENT : RPI5_PCIE_RC_DEPENDENCY));
        assert(!f.calls && (mutation == 1 || f.rc.state == RPI5_PCIE_RC_EMPTY));
    }
    prepare(&f); f.windows.io.read32 = 0;
    assert(rejected(&f) == RPI5_PCIE_RC_DEPENDENCY && !f.calls);
    prepare(&f);
    assert(rpi5_pcie_rc_configure(&f.rc,0) == RPI5_PCIE_RC_ARGUMENT && !f.calls);
    assert(rpi5_pcie_rc_configure(0,&out) == RPI5_PCIE_RC_ARGUMENT);
}
static void composition_tests(void)
{
    for (unsigned fallback = 0; fallback < 2; fallback++) {
        struct fixture f;
        struct rpi5_pcie_rc_observation rc;
        struct rpi5_pcie_ubus_observation ubus;
        struct rpi5_pcie_link_observation link;
        prepare(&f); f.fallback = fallback;
        assert(!rpi5_pcie_rc_configure(&f.rc,&rc));
        /* Reset/calibration/SerDes are modeled COMPLETE, not executed here. */
        f.serdes.state = RPI5_PCIE_SERDES_COMPLETE;
        f.serdes.bridge_reset = &f.reset; f.serdes.calibration = &f.rescal;
        f.serdes.mdio.state = RPI5_PCIE_MDIO_READY;
        f.serdes.mdio.io = (struct rpi5_pcie_mdio_io){&f,0x1000120000,0x9310,
            read32,write32,order,now_us,delay_us};
        assert(!rpi5_pcie_ubus_init(&f.ubus,&f.serdes));
        f.timed = 1;
        assert(!rpi5_pcie_ubus_configure(&f.ubus,&ubus));
        assert(ubus.outstanding_fallback == fallback);
        struct rpi5_pcie_link_io io = {check_link,read16,write16,&f.rc};
        assert(!rpi5_pcie_link_init(&f.link,&f.ubus,&f.windows,&io));
        f.link_phase = 1;
        assert(!rpi5_pcie_link_train(&f.link,&link));
        assert(link.generation == 2 && link.lanes == 4 && link.poll_reads == 1);
        assert(f.rc.state == RPI5_PCIE_RC_COMPLETE && f.link.state == RPI5_PCIE_LINK_COMPLETE);
        assert(f.regs[0xbc/4] == 0x30420440 && f.regs[0xdc/4] == 0x1234b5a2);
        assert(f.regs[0x4064/4] == 0x10203004 && f.regs[0x043c/4] == 0xab060400);
    }
}
int main(void)
{
    rc_tests(); composition_tests();
    puts("PCIE_RC_HOST_PASS FAILURE_POSITIONS=146 COMPOSED=RC_WINDOWS_UBUS_LINK");
    return 0;
}
