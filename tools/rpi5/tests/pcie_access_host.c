/* SPDX-License-Identifier: BSD-2-Clause */
/* Callback sequencing/failure model, not actual CPU/MMIO/watchdog behavior. */
#include "pcie_access.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const uint64_t addresses[] = {
    0x1001504338,0x1000119500,0x1000119508,
    0x1000124068,0x1000124064,0x100012406c,0x1000124008,0x100012043c,
    0x1000120188,0x10001204dc,0x10001200dc,0x10001200be,0x10001200bc,
    0x1000124304,0x100012184c
};
struct model {
    struct rpi5_pcie_access *s;
    unsigned calls, failure, arm_count, before_count, read_count, after_count;
    unsigned bad_read, wide_read, bad_clock, late_clock, stalled;
    uint64_t ticks;
};
static int step(struct model *m)
{
    assert(m->s->state == RPI5_PCIE_ACCESS_BUSY);
    m->calls++;
    struct rpi5_pcie_access_observation out;
    assert(rpi5_pcie_access_capture(m->s,&out) == RPI5_PCIE_ACCESS_STATE);
    return m->calls == m->failure ? -1 : 0;
}
static int arm(void *ctx) { struct model *m=ctx; m->arm_count++; return step(m); }
static int guard(void *ctx) { return step(ctx); }
static int now(void *ctx, uint64_t *value)
{
    struct model *m=ctx;
    if (step(m)) return -1;
    if (!m->stalled) m->ticks += 100;
    *value = m->calls == m->bad_clock ? 0 : m->calls == m->late_clock ? m->ticks+5000001 : m->ticks;
    return 0;
}
static int before(void *ctx, unsigned pass, unsigned index, uint64_t address, unsigned width)
{
    struct model *m=ctx;
    if (step(m)) return -1;
    assert(pass == m->before_count/15 && index == m->before_count%15);
    assert(address == addresses[index] && width == (index >= 10 && index <= 12 ? 2u : 4u));
    assert(m->read_count == m->after_count && m->before_count == m->read_count);
    m->before_count++;
    return 0;
}
static int load(void *ctx, uint64_t address, unsigned width, uint32_t *value)
{
    struct model *m=ctx;
    if (step(m)) return -1;
    assert(m->before_count == m->read_count+1 && m->after_count == m->read_count);
    unsigned index=m->read_count%15;
    assert(address == addresses[index] && width == (index >= 10 && index <= 12 ? 2u : 4u));
    m->read_count++;
    *value = m->read_count*3;
    if (m->read_count == m->bad_read) *value = width == 2 ? UINT16_MAX : UINT32_MAX;
    if (m->read_count == m->wide_read) *value = UINT16_MAX+1u;
    return 0;
}
static int after(void *ctx, unsigned pass, unsigned index, uint32_t value)
{
    struct model *m=ctx;
    if (step(m)) return -1;
    assert(pass == m->after_count/15 && index == m->after_count%15);
    assert(m->read_count == m->after_count+1 && value == m->read_count*3);
    m->after_count++;
    return 0;
}
static void prepare(struct model *m, struct rpi5_pcie_access *s, struct rpi5_pcie_fdt *fdt)
{
    memset(m,0,sizeof *m); memset(s,0,sizeof *s); memset(fdt,0,sizeof *fdt);
    m->s=s; m->ticks=1000000;
    fdt->bridge_regs=(struct rpi5_range){0x1000120000,0x1000129310};
    fdt->rescal_regs=(struct rpi5_range){0x1000119500,0x1000119510};
    fdt->bridge_reset_regs=(struct rpi5_range){0x1001504318,0x1001504348};
    fdt->bridge_reset_id=44;
    const struct rpi5_pcie_access_io io={m,arm,guard,now,before,load,after};
    assert(!rpi5_pcie_access_init(s,fdt,&io));
    assert(!m->calls && s->state == RPI5_PCIE_ACCESS_READY);
}
static void reject(struct model *m, int rc)
{
    struct rpi5_pcie_access_observation out,before;
    memset(&out,0xa5,sizeof out); before=out;
    assert(rpi5_pcie_access_capture(m->s,&out) == rc);
    assert(!memcmp(&out,&before,sizeof out));
    assert(m->s->state == RPI5_PCIE_ACCESS_QUARANTINED);
    unsigned count=m->calls;
    assert(rpi5_pcie_access_capture(m->s,&out) == RPI5_PCIE_ACCESS_STATE);
    assert(m->calls == count && m->arm_count == 1);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_access s;
    struct rpi5_pcie_fdt fdt;
    struct rpi5_pcie_access_observation out;
    prepare(&m,&s,&fdt);
    assert(!rpi5_pcie_access_capture(&s,&out));
    assert(m.calls == 184 && s.completed_callbacks == 184 && m.arm_count == 1);
    assert(m.read_count == 30 && m.before_count == 30 && m.after_count == 30);
    assert(s.state == RPI5_PCIE_ACCESS_COMPLETE && out.elapsed_us == 6100);
    for (unsigned pass=0;pass<2;pass++) for (unsigned i=0;i<15;i++)
        assert(out.values[pass][i] == (pass*15+i+1)*3);
    assert(rpi5_pcie_access_capture(&s,&out) == RPI5_PCIE_ACCESS_STATE && m.calls == 184);
    for (unsigned at=1;at<=184;at++) {
        prepare(&m,&s,&fdt); m.failure=at;
        reject(&m,RPI5_PCIE_ACCESS_IO); assert(m.calls == at && s.completed_callbacks == at-1);
    }
    for (unsigned at=1;at<=30;at++) {
        prepare(&m,&s,&fdt); m.bad_read=at;
        reject(&m,RPI5_PCIE_ACCESS_VALUE); assert(m.after_count == at-1 && m.read_count == at);
        if ((at-1)%15 >= 10 && (at-1)%15 <= 12) {
            prepare(&m,&s,&fdt); m.wide_read=at; reject(&m,RPI5_PCIE_ACCESS_VALUE);
        }
    }
    /* Every post-start clock sample, including the final guard's sample. */
    for (unsigned at=4;at<=184;at++) if ((at>=4 && (at-4)%6 == 0) ||
        (at>=8 && (at-8)%6 == 0) || at == 184) {
        prepare(&m,&s,&fdt); m.bad_clock=at; reject(&m,RPI5_PCIE_ACCESS_CLOCK);
        prepare(&m,&s,&fdt); m.late_clock=at; reject(&m,RPI5_PCIE_ACCESS_TIMEOUT);
    }
    prepare(&m,&s,&fdt); m.stalled=1; reject(&m,RPI5_PCIE_ACCESS_CLOCK);
    for (unsigned mutation=0;mutation<13;mutation++) {
        prepare(&m,&s,&fdt); memset(&s,0,sizeof s);
        struct rpi5_pcie_access_io io={&m,arm,guard,now,before,load,after};
        if (mutation == 0) fdt.bridge_regs.start++;
        if (mutation == 1) fdt.bridge_regs.end++;
        if (mutation == 2) fdt.rescal_regs.start++;
        if (mutation == 3) fdt.rescal_regs.end++;
        if (mutation == 4) fdt.bridge_reset_regs.start++;
        if (mutation == 5) fdt.bridge_reset_regs.end++;
        if (mutation == 6) fdt.bridge_reset_id=43;
        if (mutation == 7) io.arm_guard=0;
        if (mutation == 8) io.check_guard=0;
        if (mutation == 9) io.now_us=0;
        if (mutation == 10) io.before_read=0;
        if (mutation == 11) io.read=0;
        if (mutation == 12) io.after_read=0;
        assert(rpi5_pcie_access_init(&s,&fdt,&io) == RPI5_PCIE_ACCESS_ARGUMENT);
        assert(!m.calls && s.state == RPI5_PCIE_ACCESS_EMPTY);
    }
    puts("PCIE_ACCESS_HOST_PASS CALLBACKS=184 READS=30");
    return 0;
}
