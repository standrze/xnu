/* SPDX-License-Identifier: BSD-2-Clause */
/* Synthetic FDT and MMIO model only, never physical PCIe acceptance. */
#include "pcie_windows.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct event { char kind; uint32_t offset; };
struct model {
    struct rpi5_pcie_windows *session;
    uint32_t regs[0x4200/4];
    struct event events[128];
    unsigned calls, writes, fail_at, bad_at, wrong_at, drift_at;
};
static void binding(struct rpi5_pcie_fdt *f)
{
    memset(f,0,sizeof *f);
    f->bridge_regs = (struct rpi5_range){0x1000120000,0x1000129310};
    f->mip_regs = (struct rpi5_range){0x1000130000,0x10001300c0};
    f->mip_target = (struct rpi5_range){0xfffffff000,0x10000000000};
    f->outbound_count = 2; f->dma_count = 3;
    f->outbound[0] = (struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0xfffffffc};
    f->outbound[1] = (struct rpi5_pcie_window){0x43000000,0x400000000,0x1c00000000,0x300000000};
    f->dma[0] = (struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0x400000};
    f->dma[1] = (struct rpi5_pcie_window){0x43000000,0x1000000000,0,0x1000000000};
    f->dma[2] = (struct rpi5_pcie_window){0x03000000,0xfffffff000,0x1000130000,0x1000};
}
static int step(struct model *m, char kind, uint32_t offset)
{
    assert(m->session->state == RPI5_PCIE_WINDOWS_BUSY && m->calls < 128);
    m->events[m->calls++] = (struct event){kind,offset};
    struct rpi5_pcie_windows_observation out;
    assert(rpi5_pcie_windows_program(m->session,&out) == RPI5_PCIE_WINDOWS_STATE);
    if (m->calls == m->drift_at) m->regs[0x402c/4] ^= 1; /* Earlier slot changes later. */
    return m->calls == m->fail_at;
}
static int check(void *context) { return step(context,'c',0) ? -1 : 0; }
static uint32_t field_bit(uint32_t offset)
{
    if (offset == 0x4070 || offset == 0x4074) return 0x10;
    return 1;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    assert(!(offset & 3) && offset < sizeof m->regs);
    if (step(m,'r',offset)) return -1;
    *value = m->regs[offset/4];
    if (m->calls == m->bad_at) *value = UINT32_MAX;
    if (m->calls == m->wrong_at) {
        if (offset == 0x4068) *value ^= 0x80;
        else if (offset == 0x4064) *value ^= 0x4;
        else *value ^= field_bit(offset);
    }
    return 0;
}
static int allowed_write(uint32_t offset)
{
    for (unsigned i = 0; i < 3; i++)
        if (offset == 0x402c+8*i || offset == 0x4030+8*i ||
            offset == 0x40ac+8*i || offset == 0x40b0+8*i) return 1;
    for (unsigned i = 0; i < 2; i++)
        if (offset == 0x400c+8*i || offset == 0x4010+8*i || offset == 0x4070+4*i ||
            offset == 0x4080+8*i || offset == 0x4084+8*i) return 1;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m = context;
    assert(allowed_write(offset)); /* Never PERST/config/BAR/DMA/unused slots. */
    int failed = step(m,'w',offset);
    m->regs[offset/4] = value; m->writes++; /* Even failed writes may take effect. */
    return failed ? -1 : 0;
}
static int order(void *context)
{
    struct model *m = context;
    assert(m->calls && m->events[m->calls-1].kind == 'w');
    return step(m,'o',0) ? -1 : 0;
}
static void prepare(struct model *m, struct rpi5_pcie_windows *s, struct rpi5_pcie_fdt *f)
{
    memset(m,0,sizeof *m); memset(s,0,sizeof *s); binding(f); m->session = s;
    for (unsigned i = 0; i < sizeof m->regs/sizeof m->regs[0]; i++) m->regs[i] = 0x12345678;
    m->regs[0x4068/4] = 0x10080; m->regs[0x4064/4] = 0xabcdef00;
    struct rpi5_pcie_windows_io io = {m,0x1000120000,0x9310,check,read32,write32,order};
    assert(!rpi5_pcie_windows_init(s,f,&io,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES));
    assert(!m->calls && s->state == RPI5_PCIE_WINDOWS_READY);
    /* Init owns the plan/io copy, not the caller's source structures. */
    memset(&io,0,sizeof io); memset(f,0,sizeof *f);
}
static void rejects(struct model *m, int expected)
{
    struct rpi5_pcie_windows_observation out,before;
    memset(&out,0xa5,sizeof out); before = out;
    assert(rpi5_pcie_windows_program(m->session,&out) == expected);
    assert(!memcmp(&out,&before,sizeof out));
    assert(m->session->state == RPI5_PCIE_WINDOWS_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_windows_program(m->session,&out) == RPI5_PCIE_WINDOWS_STATE);
    assert(rpi5_pcie_windows_init(m->session,0,&m->session->io,RPI5_PCIE_WINDOW_EXACT) == RPI5_PCIE_WINDOWS_STATE);
    assert(calls == m->calls);
}
static void plan_rejects(struct rpi5_pcie_fdt *f, enum rpi5_pcie_window_padding padding)
{
    struct rpi5_pcie_window_plan out,before;
    memset(&out,0xa5,sizeof out); before = out;
    assert(rpi5_pcie_windows_plan(f,padding,&out) == RPI5_PCIE_WINDOWS_ARGUMENT);
    assert(!memcmp(&out,&before,sizeof out));
}
static void planner_tests(void)
{
    struct rpi5_pcie_fdt f;
    struct rpi5_pcie_window_plan p;
    binding(&f);
    plan_rejects(&f,RPI5_PCIE_WINDOW_EXACT);
    assert(!rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&p));
    assert(p.outbound[0].declared_end == 0x1ffffffffc && p.outbound[0].decode_end == 0x2000000000);
    assert(p.outbound[0].padding_bytes == 4 && p.outbound[1].padding_bytes == 0);
    assert(p.outbound[0].pci_lo == 0 && p.outbound[0].pci_hi == 0);
    assert(p.outbound[0].base_limit == 0xfff00000 && p.outbound[0].base_hi == 0x1f && p.outbound[0].limit_hi == 0x1f);
    assert(p.outbound[1].base_limit == 0xfff00000 && p.outbound[1].base_hi == 0x1c && p.outbound[1].limit_hi == 0x1e);
    assert(p.outbound[1].pci_lo == 0 && p.outbound[1].pci_hi == 4);
    assert(p.inbound[0].bar_lo == 7 && p.inbound[0].bar_hi == 0 && p.inbound[0].remap_lo == 1 && p.inbound[0].remap_hi == 0x1f);
    assert(p.inbound[1].bar_lo == 21 && p.inbound[1].bar_hi == 0x10 && p.inbound[1].remap_lo == 1 && p.inbound[1].remap_hi == 0);
    assert(p.inbound[2].bar_lo == 0xfffff01c && p.inbound[2].bar_hi == 0xff &&
        p.inbound[2].remap_lo == 0x130001 && p.inbound[2].remap_hi == 0x10);
    /* Exact boundary at the 40-bit top, with no rounding/wrap. */
    f.outbound[0].size = 0x100000000;
    f.outbound[1].cpu_base = 0xfffff00000; f.outbound[1].size = 0x100000;
    assert(!rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_EXACT,&p));
    assert(p.outbound[1].decode_end == 0x10000000000 && p.outbound[1].base_hi == 0xff && p.outbound[1].limit_hi == 0xff);
    for (unsigned exponent = 12; exponent <= 36; exponent++) {
        binding(&f);
        unsigned slot = exponent <= 32 ? 0 : 1;
        f.dma[slot].size = UINT64_C(1) << exponent;
        assert(!rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&p));
        unsigned encoded = exponent <= 15 ? exponent-12+0x1c : exponent-15;
        assert((p.inbound[slot].bar_lo & 31) == encoded);
    }
    for (unsigned bad = 0; bad < 31; bad++) {
        binding(&f);
        switch (bad) {
            case 0: f.bridge_regs.start++; break;
            case 1: f.bridge_regs.end--; break;
            case 2: f.outbound_count = 3; break;
            case 3: f.dma_count = 2; break;
            case 4: f.outbound[0].space = 0x43000000; break;
            case 5: f.outbound[1].space = 0x03000000; break;
            case 6: f.outbound[0].cpu_base++; break;
            case 7: f.outbound[1].pci_base++; break;
            case 8: f.outbound[0].size--; break; /* Arbitrary 5-byte padding rejected. */
            case 9: f.outbound[1].size--; break;
            case 10: f.outbound[0].size = 0; break;
            case 11: f.outbound[1].size = UINT64_MAX; break;
            case 12: f.outbound[1].cpu_base = 0x10000000000; break;
            case 13: f.outbound[1].pci_base = 0x10000000000; break;
            case 14: f.outbound[0].pci_base = 0x100000000; break;
            case 15: f.outbound[1].cpu_base = 0x1f00000000; break;
            case 16: f.outbound[1].pci_base = 0; break; /* Mixed flags still collide. */
            case 17: f.dma[0].size = 0x800; break;
            case 18: f.dma[0].size = 0x3000; break;
            case 19: f.dma[1].size = UINT64_C(1) << 37; break;
            case 20: f.dma[0].pci_base = 0x1000; break;
            case 21: f.dma[1].cpu_base = 1; break;
            case 22: f.dma[1].pci_base = 0; break;
            case 23: f.dma[1].cpu_base = 0x10000000000; break;
            case 24: f.dma[0].cpu_base = 0; break;
            case 25: f.dma[1].space = 0x03000000; break;
            case 26: f.mip_target.start--; break;
            case 27: f.mip_target.end--; break;
            case 28: f.mip_regs.start += 0x1000; break;
            case 29: f.mip_regs.end++; break;
            case 30: f.dma[2].size = 0x2000; break;
        }
        plan_rejects(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES);
    }
    binding(&f); plan_rejects(&f,(enum rpi5_pcie_window_padding)2);
    plan_rejects(0,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES);
    assert(rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,0) == RPI5_PCIE_WINDOWS_ARGUMENT);
}
int main(void)
{
    planner_tests();
    struct model m;
    struct rpi5_pcie_windows s;
    struct rpi5_pcie_fdt f;
    struct rpi5_pcie_windows_observation out;
    prepare(&m,&s,&f);
    uint32_t old[0x4200/4]; memcpy(old,m.regs,sizeof old);
    assert(!rpi5_pcie_windows_program(&s,&out));
    assert(m.calls == 112 && s.completed_callbacks == 112 && m.writes == 22);
    assert(s.state == RPI5_PCIE_WINDOWS_COMPLETE && out.completed_callbacks == 112 &&
        out.inbound_programmed == 3 && out.outbound_programmed == 2 && out.padding_bytes == 4);
    assert(out.final_status == 0x10080 && out.final_control == 0xabcdef00);
    for (unsigned i = 0; i < sizeof m.regs/sizeof m.regs[0]; i++)
        if (!allowed_write(4*i)) assert(old[i] == m.regs[i]);
    for (unsigned i = 0; i < 2; i++) {
        uint32_t at = (0x4070+4*i)/4;
        assert((m.regs[at] & ~0xfff0fff0u) == (old[at] & ~0xfff0fff0u));
        at = (0x4080+8*i)/4; assert((m.regs[at] & ~0xffu) == (old[at] & ~0xffu));
        at = (0x4084+8*i)/4; assert((m.regs[at] & ~0xffu) == (old[at] & ~0xffu));
    }
    assert(rpi5_pcie_windows_program(&s,&out) == RPI5_PCIE_WINDOWS_STATE && m.calls == 112);
    struct event events[128]; memcpy(events,m.events,sizeof events);
    for (unsigned at = 1; at <= 112; at++) {
        prepare(&m,&s,&f); m.fail_at = at;
        rejects(&m,events[at-1].kind == 'c' ? RPI5_PCIE_WINDOWS_NOT_QUIESCENT : RPI5_PCIE_WINDOWS_IO);
        assert(m.calls == at && s.completed_callbacks == at-1);
        if (events[at-1].kind == 'r') {
            prepare(&m,&s,&f); m.bad_at = at;
            rejects(&m,RPI5_PCIE_WINDOWS_READBACK); assert(m.calls == at);
            /* Initial RMW reads accept observed target bits, not fixed values. */
            if (at < 112 && events[at].kind == 'w' && events[at].offset == events[at-1].offset) continue;
            prepare(&m,&s,&f); m.wrong_at = at;
            rejects(&m,events[at-1].offset == 0x4068 || events[at-1].offset == 0x4064 ?
                RPI5_PCIE_WINDOWS_NOT_QUIESCENT : RPI5_PCIE_WINDOWS_READBACK);
            assert(m.calls == at);
        }
    }
    prepare(&m,&s,&f); m.drift_at = 87;
    rejects(&m,RPI5_PCIE_WINDOWS_READBACK); assert(m.calls == 88); /* Independent final pass. */
    for (unsigned bad = 0; bad < 6; bad++) {
        prepare(&m,&s,&f);
        if (bad == 0) m.regs[0x4068/4] &= ~0x80u;
        if (bad == 1) m.regs[0x4068/4] |= 0x10;
        if (bad == 2) m.regs[0x4068/4] |= 0x20;
        if (bad == 3) m.regs[0x4068/4] |= 0x40;
        if (bad == 4) m.regs[0x4064/4] |= 0x4;
        if (bad == 5) m.regs[0x4064/4] |= 0x1;
        rejects(&m,RPI5_PCIE_WINDOWS_NOT_QUIESCENT); assert(m.calls == (bad < 4 ? 2u : 3u) && !m.writes);
    }
    for (unsigned bad = 0; bad < 6; bad++) {
        prepare(&m,&s,&f);
        struct rpi5_pcie_windows_io io = s.io;
        if (bad == 0) io.physical_base++;
        if (bad == 1) io.mapped_bytes--;
        if (bad == 2) io.check_quiescent = 0;
        if (bad == 3) io.read32 = 0;
        if (bad == 4) io.write32 = 0;
        if (bad == 5) io.order = 0;
        memset(&s,0,sizeof s); struct rpi5_pcie_windows before = s; binding(&f);
        assert(rpi5_pcie_windows_init(&s,&f,&io,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES) == RPI5_PCIE_WINDOWS_ARGUMENT);
        assert(!memcmp(&s,&before,sizeof s) && !m.calls);
    }
    prepare(&m,&s,&f);
    assert(rpi5_pcie_windows_program(&s,0) == RPI5_PCIE_WINDOWS_ARGUMENT && !m.calls && s.state == RPI5_PCIE_WINDOWS_READY);
    puts("PCIE_WINDOWS_HOST_PASS");
    return 0;
}
