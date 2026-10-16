/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_reset.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    unsigned calls, fail_at, bad_at, asserts, clears, statuses, wrong_bit_at;
    uint32_t bank;
    char trace[16];
    struct rpi5_pcie_reset *session;
};

static int step(struct model *m, char operation)
{
    assert(m->session->state == RPI5_PCIE_RESET_BUSY);
    assert(m->calls < sizeof m->trace);
    m->trace[m->calls++] = operation;
    /* Reentry must reject before another I/O callback. */
    struct rpi5_pcie_reset_observation unused;
    assert(rpi5_pcie_reset_pulse(m->session, &unused) == RPI5_PCIE_RESET_STATE);
    return m->calls == m->fail_at;
}
static int status(void *context, uint32_t *value)
{
    struct model *m = context;
    if (step(m, 'R')) return -1;
    m->statuses++;
    *value = m->calls == m->bad_at ? UINT32_MAX : m->bank;
    if (m->calls == m->wrong_bit_at) *value ^= 0x1000;
    return 0;
}
static int assert_bridge(void *context)
{
    struct model *m = context;
    int failed = step(m, 'S');
    /* A failing write can still have taken effect: never undo/retry it. */
    m->bank |= 0x1000;
    m->asserts++;
    return failed ? -1 : 0;
}
static int deassert_bridge(void *context)
{
    struct model *m = context;
    int failed = step(m, 'C');
    m->bank &= ~0x1000u;
    m->clears++;
    return failed ? -1 : 0;
}
static int order(void *context) { return step(context, 'O') ? -1 : 0; }
static int delay_us(void *context, uint32_t us)
{
    assert(us == 100);
    return step(context, 'D') ? -1 : 0;
}
static struct rpi5_pcie_fdt topology(void)
{
    struct rpi5_pcie_fdt fdt = {0};
    fdt.bridge_reset_regs = (struct rpi5_range){0x1001504318, 0x1001504348};
    fdt.bridge_reset_id = 44;
    return fdt;
}
static struct rpi5_pcie_reset_io provider(struct model *m)
{
    struct rpi5_pcie_reset_io io = {
        m, 0x1001504318, 0x30, status, assert_bridge, deassert_bridge, order, delay_us
    };
    return io;
}
static void prepare(struct model *m, struct rpi5_pcie_reset *session)
{
    memset(m, 0, sizeof *m);
    memset(session, 0, sizeof *session);
    m->bank = 0x87654321u & ~0x1000u;
    m->session = session;
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_reset_io io = provider(m);
    assert(!rpi5_pcie_reset_init(session, &fdt, &io));
    assert(!m->calls && session->state == RPI5_PCIE_RESET_READY);
}
static void rejects(struct model *m, struct rpi5_pcie_reset *session, int rc)
{
    struct rpi5_pcie_reset_observation out, before;
    memset(&before, 0xa5, sizeof before); out = before;
    assert(rpi5_pcie_reset_pulse(session, &out) == rc);
    assert(!memcmp(&out, &before, sizeof out));
    assert(session->state == RPI5_PCIE_RESET_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_reset_pulse(session, &out) == RPI5_PCIE_RESET_STATE);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_reset_io io = provider(m);
    assert(rpi5_pcie_reset_init(session, &fdt, &io) == RPI5_PCIE_RESET_STATE);
    assert(m->calls == calls);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_reset session;
    struct rpi5_pcie_reset_observation out;
    prepare(&m, &session);
    uint32_t bank = m.bank;
    assert(!rpi5_pcie_reset_pulse(&session, &out));
    assert(m.calls == 9 && !memcmp(m.trace, "RSODRCODR", 9));
    assert(m.asserts == 1 && m.clears == 1 && m.statuses == 3);
    assert(out.before == bank && out.asserted == (bank | 0x1000) && out.released == bank);
    assert(m.bank == bank && session.completed_callbacks == 9);
    assert(session.state == RPI5_PCIE_RESET_COMPLETE);
    assert(rpi5_pcie_reset_pulse(&session, &out) == RPI5_PCIE_RESET_STATE);
    assert(m.calls == 9);

    prepare(&m, &session); m.bank |= 0x1000; /* already asserted is allowed */
    assert(!rpi5_pcie_reset_pulse(&session, &out));
    assert(!(out.released & 0x1000));
    for (unsigned fail = 1; fail <= 9; fail++) {
        prepare(&m, &session); m.fail_at = fail;
        rejects(&m, &session, RPI5_PCIE_RESET_IO);
        assert(m.calls == fail && session.completed_callbacks == fail - 1);
    }
    const unsigned reads[] = {1, 5, 9};
    for (unsigned i = 0; i < 3; i++) {
        prepare(&m, &session); m.bad_at = reads[i];
        rejects(&m, &session, RPI5_PCIE_RESET_READBACK);
        assert(m.calls == reads[i]);
    }
    prepare(&m, &session); m.wrong_bit_at = 5;
    rejects(&m, &session, RPI5_PCIE_RESET_READBACK);
    assert(m.calls == 5 && !m.clears);
    prepare(&m, &session); m.wrong_bit_at = 9;
    rejects(&m, &session, RPI5_PCIE_RESET_READBACK);
    assert(m.calls == 9 && m.clears == 1);

    /* Every missing provider function, incorrect resource or ID rejects with
     * no mutation and zero callback use. */
    for (unsigned bad = 0; bad < 10; bad++) {
        prepare(&m, &session);
        struct rpi5_pcie_fdt fdt = topology();
        struct rpi5_pcie_reset_io io = provider(&m);
        memset(&session, 0, sizeof session);
        struct rpi5_pcie_reset before = session;
        switch (bad) {
            case 0: io.status = NULL; break;
            case 1: io.assert_bridge = NULL; break;
            case 2: io.deassert_bridge = NULL; break;
            case 3: io.order = NULL; break;
            case 4: io.delay_us = NULL; break;
            case 5: io.physical_base++; break;
            case 6: io.mapped_bytes--; break;
            case 7: fdt.bridge_reset_id = 43; break;
            case 8: fdt.bridge_reset_regs.start++; break;
            case 9: fdt.bridge_reset_regs.end++; break;
        }
        assert(rpi5_pcie_reset_init(&session, &fdt, &io) == RPI5_PCIE_RESET_ARGUMENT);
        assert(!memcmp(&session, &before, sizeof session) && !m.calls);
    }
    memset(&session, 0, sizeof session);
    assert(rpi5_pcie_reset_pulse(&session, &out) == RPI5_PCIE_RESET_STATE);
    assert(rpi5_pcie_reset_pulse(NULL, &out) == RPI5_PCIE_RESET_ARGUMENT);
    assert(rpi5_pcie_reset_pulse(&session, NULL) == RPI5_PCIE_RESET_ARGUMENT);
    puts("PCIE_RESET_HOST_PASS");
    return 0;
}
