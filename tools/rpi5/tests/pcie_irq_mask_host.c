/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_irq_mask.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_irq_mask session;
    uint32_t gic[1024], calls, fail_at, writes, orders, read_count;
    uint32_t write_offset[3], write_value[3];
    int reenter, ignore_write, change_pending, change_nvme, drift_typer;
};
static int callback(struct model *m)
{
    m->calls++;
    if (m->reenter) {
        struct rpi5_pcie_irq_observation out;
        unsigned calls = m->calls;
        assert(rpi5_pcie_irq_begin(&m->session, &out) == -1);
        assert(rpi5_pcie_irq_check(&m->session, &out) == -1);
        assert(m->calls == calls);
    }
    return m->calls == m->fail_at ? -1 : 0;
}
static int owner(void *context) { return callback(context); }
static int read32(void *context, uint32_t offset, uint32_t *out)
{
    struct model *m = context;
    assert(offset == 4 || offset == 0x114 || offset == 0x118 || offset == 0x120 ||
        offset == 0x214 || offset == 0x218 || offset == 0x220 ||
        offset == 0x314 || offset == 0x318 || offset == 0x320);
    if (callback(m)) return -1;
    if (m->change_pending && offset == 0x214) m->gic[offset/4] ^= 1;
    if (m->change_nvme && (offset == 0x120 || offset == 0x220 || offset == 0x320))
        m->gic[offset/4] ^= UINT32_C(0x7f800001);
    if (m->drift_typer && offset == 4 && m->read_count) m->gic[1] ^= 0x20;
    *out = m->gic[offset/4]; m->read_count++;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m = context;
    assert(m->writes < 3);
    assert((offset == 0x194 || offset == 0x198) ? value == UINT32_MAX : offset == 0x1a0 && value == 0x7e0);
    m->write_offset[m->writes] = offset; m->write_value[m->writes++] = value;
    if (!m->ignore_write) m->gic[(offset-0x80)/4] &= ~value;
    return callback(m); /* An error return may follow a visible write. */
}
static int order(void *context)
{
    struct model *m = context; m->orders++;
    return callback(m);
}
static struct rpi5_pcie_fdt binding(void)
{
    struct rpi5_pcie_fdt b = {0};
    b.bridge_regs = (struct rpi5_range){UINT64_C(0x1000120000),UINT64_C(0x1000129310)};
    b.bridge_reset_id = 44; b.gic_phandle = 1;
    b.bridge_intid[0] = 265; b.bridge_intid[1] = 266;
    b.mip_intid_base = 160; b.mip_intid_count = 64;
    for (unsigned i = 0; i < 4; i++) b.intx_intid[i] = 261+i;
    return b;
}
static void prepare(struct model *m)
{
    memset(m, 0, sizeof(*m));
    m->gic[1] = 15;
    m->gic[0x114/4] = UINT32_MAX; m->gic[0x118/4] = UINT32_MAX;
    m->gic[0x120/4] = UINT32_MAX; m->gic[0x220/4] = UINT32_MAX;
    m->gic[0x320/4] = UINT32_C(0x7f800001); /* NVMe active bits may remain set. */
    struct rpi5_pcie_irq_io io = {m, UINT64_C(0x107fff9000),0x1000,owner,read32,write32,order};
    struct rpi5_pcie_fdt b = binding();
    assert(!rpi5_pcie_irq_init(&m->session, &b, &io));
    assert(!m->calls && m->session.state == RPI5_PCIE_IRQ_READY);
}
static void reject(struct model *m, int begin)
{
    struct rpi5_pcie_irq_observation out, sentinel;
    memset(&sentinel, 0xa5, sizeof(sentinel)); out = sentinel;
    assert((begin ? rpi5_pcie_irq_begin(&m->session, &out) : rpi5_pcie_irq_check(&m->session, &out)) == -1);
    assert(!memcmp(&out, &sentinel, sizeof(out)));
    assert(m->session.state == RPI5_PCIE_IRQ_QUARANTINED);
    unsigned calls = m->calls, writes = m->writes;
    assert(rpi5_pcie_irq_begin(&m->session, &out) == -1);
    assert(rpi5_pcie_irq_check(&m->session, &out) == -1);
    assert(m->calls == calls && m->writes == writes);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_irq_observation out;
    prepare(&m); m.reenter = 1;
    assert(!rpi5_pcie_irq_begin(&m.session, &out));
    assert(out.callbacks == 106 && m.calls == 106 && m.writes == 3 && m.orders == 3);
    assert(out.enabled_before[0] == UINT32_MAX && out.enabled_before[2] == UINT32_MAX);
    assert(m.gic[0x120/4] == (UINT32_MAX ^ UINT32_C(0x7e0)));
    assert(m.gic[0x220/4] == UINT32_MAX && m.gic[0x320/4] == UINT32_C(0x7f800001));
    assert(m.write_offset[0] == 0x194 && m.write_offset[1] == 0x198 && m.write_offset[2] == 0x1a0);
    unsigned calls = m.calls;
    assert(rpi5_pcie_irq_begin(&m.session, &out) == -1 && m.calls == calls);
    m.change_pending = m.change_nvme = 1;
    assert(!rpi5_pcie_irq_check(&m.session, &out));
    assert(out.callbacks == 61 && m.calls-calls == 61 && m.writes == 3);
    assert(out.pending[0][0] != out.pending[1][0]);
    for (unsigned position = 1; position <= 106; position++) {
        prepare(&m); m.fail_at = position;
        reject(&m, 1);
        assert(m.calls == position && m.writes <= 3);
    }
    for (unsigned position = 1; position <= 61; position++) {
        prepare(&m); assert(!rpi5_pcie_irq_begin(&m.session, &out));
        m.calls = 0; m.fail_at = position;
        reject(&m, 0);
        assert(m.calls == position && m.writes == 3);
    }
    for (unsigned bank = 0; bank < 3; bank++) {
        prepare(&m);
        m.gic[(0x300+4*(bank < 2 ? bank+5 : 8))/4] |= bank == 2 ? 0x20 : 1;
        reject(&m, 1); assert(!m.writes);
    }
    prepare(&m); m.ignore_write = 1; reject(&m, 1); assert(m.writes == 3);
    prepare(&m); m.gic[1] = 7; reject(&m, 1); assert(!m.writes);
    prepare(&m); m.gic[1] = UINT32_MAX; reject(&m, 1); assert(!m.writes);
    prepare(&m); m.drift_typer = 1; reject(&m, 1);
    for (unsigned kind = 0; kind < 2; kind++) {
        prepare(&m); assert(!rpi5_pcie_irq_begin(&m.session, &out));
        m.gic[(kind ? 0x314 : 0x114)/4] = 1;
        reject(&m, 0);
    }
    prepare(&m);
    assert(rpi5_pcie_irq_begin(&m.session, (void *)&m.session) == -1 && !m.calls);
    assert(rpi5_pcie_irq_check(&m.session, &out) == -1 && !m.calls);
    for (unsigned change = 0; change < 10; change++) {
        memset(&m.session, 0, sizeof(m.session));
        struct rpi5_pcie_fdt b = binding();
        struct rpi5_pcie_irq_io io = {&m,UINT64_C(0x107fff9000),0x1000,owner,read32,write32,order};
        switch (change) {
        case 0: b.bridge_intid[0] = 256; break;
        case 1: b.intx_intid[3] = 256; break;
        case 2: b.mip_intid_count = 63; break;
        case 3: b.mip_intid_base = 161; break;
        case 4: b.bridge_reset_id = 43; break;
        case 5: b.gic_phandle = 0; break;
        case 6: io.physical_base++; break;
        case 7: io.mapped_bytes++; break;
        case 8: io.order = NULL; break;
        case 9: io.check_owner = NULL; break;
        }
        assert(rpi5_pcie_irq_init(&m.session, &b, &io) == -1);
        assert(m.session.state == RPI5_PCIE_IRQ_EMPTY);
    }
    puts("PCIE_IRQ_MASK_HOST_PASS BEGIN_FAILURES=106 CHECK_FAILURES=61 W1C_WRITES=3 NO_NVME_WRITES=1 NO_MMIO=1");
    return 0;
}
