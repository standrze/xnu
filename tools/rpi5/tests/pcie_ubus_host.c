/* SPDX-License-Identifier: BSD-2-Clause */
/* Callback model only. COMPLETE prerequisites are not hardware evidence. */
#include "pcie_ubus.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_ubus *session;
    unsigned calls, fail_at, bad_at, wrong_at, reserved, writes, fallback_writes;
    uint32_t ubus, error_data, timeout, retry, axi, ctrl;
};
static int step(struct model *m)
{
    assert(m->session->state == RPI5_PCIE_UBUS_BUSY);
    m->calls++;
    struct rpi5_pcie_ubus_observation out;
    assert(rpi5_pcie_ubus_configure(m->session, &out) == RPI5_PCIE_UBUS_STATE);
    return m->calls == m->fail_at;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    if (step(m)) return -1;
    uint32_t wrong = 1;
    switch (offset) {
        case 0x40a4: *value = m->ubus; wrong = 0x2000; break;
        case 0x40a8: *value = m->timeout; break;
        case 0x405c: *value = m->retry; break;
        case 0x416c: *value = m->axi; wrong = m->calls == 19 ? 1 : 0x2000; break;
        case 0x40a0: *value = m->ctrl; wrong = 0x20; break;
        default: assert(0); /* No config selectors, PERST or error-data read. */
    }
    if (m->calls == m->bad_at) *value = UINT32_MAX;
    if (m->calls == m->wrong_at) *value ^= wrong;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m = context;
    int failed = step(m);
    m->writes++;
    switch (offset) {
        case 0x40a4: assert(value == (m->ubus | 0x82000)); m->ubus = value; break;
        case 0x4170: assert(value == UINT32_MAX); m->error_data = value; break;
        case 0x40a8: assert(value == 0x0b2d0000); m->timeout = value; break;
        case 0x405c: assert(value == 0x0aba0000); m->retry = value; break;
        case 0x416c:
            if (m->calls == 14) {
                assert(value == ((m->axi & ~0x80u) | 0x3800));
            } else {
                assert(m->reserved && m->calls == 17);
                assert(value == ((m->axi & ~0x3fu) | 15)); m->fallback_writes++;
            }
            m->axi = value & ~(m->reserved ? 0x1000u : 0u);
            break;
        case 0x40a0: assert(value == (m->ctrl & ~0x20u)); m->ctrl = value; break;
        default: assert(0); /* No windows, bus mastering, IRQ or DMA. */
    }
    return failed ? -1 : 0; /* Failed writes may still have taken effect. */
}
static int order(void *context) { return step(context) ? -1 : 0; }
static void prepare(struct model *m, struct rpi5_pcie_ubus *session,
    struct rpi5_pcie_serdes *serdes, struct rpi5_pcie_rescal *rescal,
    struct rpi5_pcie_reset *reset, unsigned reserved)
{
    memset(m,0,sizeof *m); memset(session,0,sizeof *session); memset(serdes,0,sizeof *serdes);
    memset(rescal,0,sizeof *rescal); memset(reset,0,sizeof *reset);
    rescal->state = RPI5_PCIE_RESCAL_COMPLETE; reset->state = RPI5_PCIE_RESET_COMPLETE;
    serdes->state = RPI5_PCIE_SERDES_COMPLETE; serdes->mdio.state = RPI5_PCIE_MDIO_READY;
    serdes->calibration = rescal; serdes->bridge_reset = reset;
    serdes->mdio.io = (struct rpi5_pcie_mdio_io){m,0x1000120000,0x9310,read32,write32,order,0,0};
    m->session = session; m->reserved = reserved;
    m->ubus = 0x12340001; m->axi = 0x900080ff; m->ctrl = 0x12345678;
    assert(!rpi5_pcie_ubus_init(session,serdes));
    assert(!m->calls && session->state == RPI5_PCIE_UBUS_READY);
}
static void rejects(struct model *m, int rc)
{
    struct rpi5_pcie_ubus_observation out,before;
    memset(&out,0xa5,sizeof out); before = out;
    assert(rpi5_pcie_ubus_configure(m->session,&out) == rc);
    assert(!memcmp(&out,&before,sizeof out));
    assert(m->session->state == RPI5_PCIE_UBUS_QUARANTINED);
    assert(m->session->serdes->state == RPI5_PCIE_SERDES_QUARANTINED);
    assert(m->session->serdes->mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_ubus_configure(m->session,&out) == RPI5_PCIE_UBUS_STATE);
    assert(rpi5_pcie_ubus_init(m->session,m->session->serdes) == RPI5_PCIE_UBUS_STATE);
    assert(calls == m->calls);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_ubus session;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_ubus_observation out;
    for (unsigned reserved = 0; reserved < 2; reserved++) {
        unsigned total = reserved ? 23 : 20;
        prepare(&m,&session,&serdes,&rescal,&reset,reserved);
        assert(!rpi5_pcie_ubus_configure(&session,&out));
        assert(m.calls == total && session.completed_callbacks == total);
        assert(session.state == RPI5_PCIE_UBUS_COMPLETE && m.error_data == UINT32_MAX);
        assert(out.ubus_before == 0x12340001 && out.ubus_after == (0x12340001 | 0x82000));
        assert(out.ubus_timeout == 0x0b2d0000 && out.config_retry_timeout == 0x0aba0000);
        uint32_t wanted = (0x900080ffu & ~0x80u) | 0x3800;
        if (reserved) wanted = (wanted & ~(0x1000u | 0x3fu)) | 15;
        assert(out.axi_before == 0x900080ff && out.axi_final == wanted);
        assert(out.outstanding_fallback == reserved && m.fallback_writes == reserved);
        assert(out.control_before == 0x12345678 && out.control_after == (0x12345678 & ~0x20));
        assert(m.writes == 6+reserved);
        assert(rpi5_pcie_ubus_configure(&session,&out) == RPI5_PCIE_UBUS_STATE);
        assert(m.calls == total);
        for (unsigned fail = 1; fail <= total; fail++) {
            prepare(&m,&session,&serdes,&rescal,&reset,reserved); m.fail_at = fail;
            rejects(&m,RPI5_PCIE_UBUS_IO); assert(m.calls == fail);
            assert(session.completed_callbacks == fail-1);
            assert(rescal.state == RPI5_PCIE_RESCAL_COMPLETE && reset.state == RPI5_PCIE_RESET_COMPLETE);
        }
        const unsigned reads[] = {1,4,9,12,13,16,17,20};
        for (unsigned i = 0; i < sizeof reads/sizeof reads[0]; i++) {
            unsigned at = reads[i];
            if (reserved && at == 17) at = 19;
            prepare(&m,&session,&serdes,&rescal,&reset,reserved); m.bad_at = at;
            rejects(&m,RPI5_PCIE_UBUS_READBACK); assert(m.calls == at);
        }
        if (reserved) {
            prepare(&m,&session,&serdes,&rescal,&reset,reserved); m.bad_at = 23;
            rejects(&m,RPI5_PCIE_UBUS_READBACK); assert(m.calls == 23);
        }
        const unsigned wrong[] = {4,9,12,16,20};
        for (unsigned i = 0; i < sizeof wrong/sizeof wrong[0]; i++) {
            unsigned at = wrong[i]; if (reserved && at == 20) at = 23;
            prepare(&m,&session,&serdes,&rescal,&reset,reserved); m.wrong_at = at;
            rejects(&m,RPI5_PCIE_UBUS_READBACK); assert(m.calls == at);
        }
        if (reserved) {
            prepare(&m,&session,&serdes,&rescal,&reset,reserved); m.wrong_at = 19;
            rejects(&m,RPI5_PCIE_UBUS_READBACK); assert(m.calls == 19);
        }
    }
    for (unsigned bad = 0; bad < 4; bad++) {
        prepare(&m,&session,&serdes,&rescal,&reset,0);
        if (bad == 0) serdes.state = RPI5_PCIE_SERDES_QUARANTINED;
        if (bad == 1) serdes.mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
        if (bad == 2) rescal.state = RPI5_PCIE_RESCAL_QUARANTINED;
        if (bad == 3) reset.state = RPI5_PCIE_RESET_QUARANTINED;
        rejects(&m,RPI5_PCIE_UBUS_DEPENDENCY); assert(!m.calls);
    }
    for (unsigned bad = 0; bad < 7; bad++) {
        prepare(&m,&session,&serdes,&rescal,&reset,0); memset(&session,0,sizeof session);
        if (bad == 0) serdes.mdio.io.physical_base++;
        if (bad == 1) serdes.mdio.io.mapped_bytes--;
        if (bad == 2) serdes.mdio.io.read32 = 0;
        if (bad == 3) serdes.mdio.io.write32 = 0;
        if (bad == 4) serdes.mdio.io.order = 0;
        if (bad == 5) serdes.calibration = 0;
        if (bad == 6) serdes.bridge_reset = 0;
        struct rpi5_pcie_ubus before = session;
        assert(rpi5_pcie_ubus_init(&session,&serdes) == (bad < 5 ? RPI5_PCIE_UBUS_ARGUMENT : RPI5_PCIE_UBUS_DEPENDENCY));
        assert(!memcmp(&session,&before,sizeof session) && !m.calls);
    }
    prepare(&m,&session,&serdes,&rescal,&reset,0);
    assert(rpi5_pcie_ubus_configure(&session,0) == RPI5_PCIE_UBUS_ARGUMENT);
    assert(session.state == RPI5_PCIE_UBUS_READY && !m.calls);
    assert(rpi5_pcie_ubus_init(0,&serdes) == RPI5_PCIE_UBUS_ARGUMENT);
    assert(rpi5_pcie_ubus_init(&session,0) == RPI5_PCIE_UBUS_ARGUMENT);
    puts("PCIE_UBUS_HOST_PASS");
    return 0;
}
