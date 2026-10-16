/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_rescal.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_rescal *session;
    unsigned calls, fail_at, all_ones_at, wrong_bit_at, writes, claims;
    unsigned status_reads, complete_at_read, clocks, backwards_at;
    uint32_t start, delay_elapsed, status_latency;
    uint64_t now;
    int claimed, stopped_clock;
    char trace[80];
};

static int step(struct model *m, char operation)
{
    assert(m->session->state == RPI5_PCIE_RESCAL_BUSY);
    assert(m->calls < sizeof m->trace);
    if (operation != 'A') assert(m->claimed);
    m->trace[m->calls++] = operation;
    struct rpi5_pcie_rescal_observation out;
    assert(rpi5_pcie_rescal_calibrate(m->session, &out) == RPI5_PCIE_RESCAL_STATE);
    return m->calls == m->fail_at;
}
static int claim(void *context)
{
    struct model *m = context;
    int failed = step(m, 'A');
    assert(!m->claimed); m->claimed = 1; m->claims++;
    return failed ? -1 : 0;
}
static int read_start(void *context, uint32_t *value)
{
    struct model *m = context;
    if (step(m, 'R')) return -1;
    *value = m->calls == m->all_ones_at ? UINT32_MAX : m->start;
    if (m->calls == m->wrong_bit_at) *value ^= 1;
    return 0;
}
static int write_start(void *context, uint32_t value)
{
    struct model *m = context;
    int failed = step(m, 'W');
    assert((value ^ m->start) == 1); /* no other control bit changes */
    m->start = value; m->writes++;
    return failed ? -1 : 0; /* may take effect despite reporting failure */
}
static int read_status(void *context, uint32_t *value)
{
    struct model *m = context;
    if (step(m, 'S')) return -1;
    m->status_reads++;
    if (!m->stopped_clock) m->now += m->status_latency;
    *value = m->calls == m->all_ones_at ? UINT32_MAX :
        0x80000000u | (m->status_reads >= m->complete_at_read);
    return 0;
}
static int order(void *context) { return step(context, 'O') ? -1 : 0; }
static int now_us(void *context, uint64_t *value)
{
    struct model *m = context;
    if (step(m, 'T')) return -1;
    m->clocks++;
    *value = m->now - (m->clocks == m->backwards_at);
    return 0;
}
static int delay_us(void *context, uint32_t interval)
{
    struct model *m = context;
    assert(interval == 100);
    if (step(m, 'D')) return -1;
    if (!m->stopped_clock) m->now += m->delay_elapsed;
    return 0;
}
static struct rpi5_pcie_fdt topology(void)
{
    struct rpi5_pcie_fdt fdt = {0};
    fdt.rescal_regs = (struct rpi5_range){0x1000119500, 0x1000119510};
    return fdt;
}
static struct rpi5_pcie_rescal_io provider(struct model *m)
{
    struct rpi5_pcie_rescal_io io = {
        m, 0x1000119500, 0x10, claim, read_start, write_start,
        read_status, order, now_us, delay_us
    };
    return io;
}
static void prepare(struct model *m, struct rpi5_pcie_rescal *session)
{
    memset(m, 0, sizeof *m); memset(session, 0, sizeof *session);
    m->session = session; m->start = 0x87654320;
    m->now = 10000; m->complete_at_read = 1; m->delay_elapsed = 100;
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_rescal_io io = provider(m);
    assert(!rpi5_pcie_rescal_init(session, &fdt, &io));
    assert(!m->calls && session->state == RPI5_PCIE_RESCAL_READY);
}
static void rejects(struct model *m, struct rpi5_pcie_rescal *session, int rc)
{
    struct rpi5_pcie_rescal_observation out, before;
    memset(&out, 0xa5, sizeof out); before = out;
    assert(rpi5_pcie_rescal_calibrate(session, &out) == rc);
    assert(!memcmp(&out, &before, sizeof out));
    assert(session->state == RPI5_PCIE_RESCAL_QUARANTINED);
    unsigned calls = m->calls;
    assert(rpi5_pcie_rescal_calibrate(session, &out) == RPI5_PCIE_RESCAL_STATE);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_rescal_io io = provider(m);
    assert(rpi5_pcie_rescal_init(session, &fdt, &io) == RPI5_PCIE_RESCAL_STATE);
    assert(calls == m->calls); /* no cleanup, retry or claim release */
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_rescal session;
    struct rpi5_pcie_rescal_observation out;
    prepare(&m, &session);
    assert(!rpi5_pcie_rescal_calibrate(&session, &out));
    assert(m.calls == 12 && !memcmp(m.trace, "ARWORTSTRWOR", 12));
    assert(m.claims == 1 && m.claimed && m.writes == 2 && m.start == 0x87654320);
    assert(out.initial_start == 0x87654320 && out.asserted_start == 0x87654321);
    assert(out.before_clear == 0x87654321 && out.cleared_start == 0x87654320);
    assert(out.completion_status == 0x80000001 && out.status_reads == 1 && !out.poll_elapsed_us);
    assert(session.state == RPI5_PCIE_RESCAL_COMPLETE && session.completed_callbacks == m.calls);
    assert(rpi5_pcie_rescal_calibrate(&session, &out) == RPI5_PCIE_RESCAL_STATE);

    for (unsigned ready = 1; ready <= 11; ready++) {
        prepare(&m, &session); m.complete_at_read = ready;
        assert(!rpi5_pcie_rescal_calibrate(&session, &out));
        assert(out.status_reads == ready && out.poll_elapsed_us == 100 * (ready - 1));
        assert(m.calls == 12 + 4 * (ready - 1) && m.writes == 2);
        unsigned total = m.calls;
        /* Fault every callback of every successful delay/poll path, including
         * side-effecting writes, ownership claim and final readback. */
        for (unsigned fail = 1; fail <= total; fail++) {
            prepare(&m, &session); m.complete_at_read = ready; m.fail_at = fail;
            rejects(&m, &session, RPI5_PCIE_RESCAL_IO);
            assert(m.calls == fail && session.completed_callbacks == fail - 1);
        }
    }
    const unsigned reads[] = {2, 5, 7, 9, 12};
    for (unsigned i = 0; i < sizeof reads / sizeof reads[0]; i++) {
        prepare(&m, &session); m.all_ones_at = reads[i];
        rejects(&m, &session, RPI5_PCIE_RESCAL_READBACK);
        assert(m.calls == reads[i]);
    }
    for (unsigned read = 5; read <= 12; read += read == 5 ? 4 : 3) {
        prepare(&m, &session); m.wrong_bit_at = read;
        rejects(&m, &session, RPI5_PCIE_RESCAL_READBACK);
        assert(m.calls == read);
    }
    prepare(&m, &session); m.start |= 1;
    rejects(&m, &session, RPI5_PCIE_RESCAL_ALREADY_STARTED);
    assert(m.calls == 2 && !m.writes);
    prepare(&m, &session); m.complete_at_read = 12;
    rejects(&m, &session, RPI5_PCIE_RESCAL_TIMEOUT);
    assert(m.status_reads == 11 && m.writes == 1 && (m.start & 1));
    prepare(&m, &session); m.complete_at_read = 2; m.delay_elapsed = 1001;
    rejects(&m, &session, RPI5_PCIE_RESCAL_TIMEOUT);
    assert(m.status_reads == 1 && m.writes == 1);
    prepare(&m, &session); m.status_latency = 1001;
    rejects(&m, &session, RPI5_PCIE_RESCAL_TIMEOUT);
    assert(m.status_reads == 1 && m.writes == 1); /* late DONE cannot pass */
    prepare(&m, &session); m.backwards_at = 2;
    rejects(&m, &session, RPI5_PCIE_RESCAL_CLOCK);
    prepare(&m, &session); m.complete_at_read = 2; m.backwards_at = 3; m.delay_elapsed = 0;
    rejects(&m, &session, RPI5_PCIE_RESCAL_CLOCK);
    prepare(&m, &session); m.stopped_clock = 1; m.complete_at_read = 12;
    rejects(&m, &session, RPI5_PCIE_RESCAL_TIMEOUT);
    assert(m.status_reads == 11); /* finite even for a broken clock */

    for (unsigned bad = 0; bad < 11; bad++) {
        prepare(&m, &session); memset(&session, 0, sizeof session);
        struct rpi5_pcie_rescal before = session;
        struct rpi5_pcie_fdt fdt = topology();
        struct rpi5_pcie_rescal_io io = provider(&m);
        switch (bad) {
            case 0: io.claim_shared = NULL; break;
            case 1: io.read_start = NULL; break;
            case 2: io.write_start = NULL; break;
            case 3: io.read_status = NULL; break;
            case 4: io.order = NULL; break;
            case 5: io.now_us = NULL; break;
            case 6: io.delay_us = NULL; break;
            case 7: io.physical_base++; break;
            case 8: io.mapped_bytes--; break;
            case 9: fdt.rescal_regs.start++; break;
            case 10: fdt.rescal_regs.end++; break;
        }
        assert(rpi5_pcie_rescal_init(&session, &fdt, &io) == RPI5_PCIE_RESCAL_ARGUMENT);
        assert(!m.calls && !memcmp(&session, &before, sizeof session));
    }
    memset(&session, 0, sizeof session);
    assert(rpi5_pcie_rescal_calibrate(&session, &out) == RPI5_PCIE_RESCAL_STATE);
    assert(rpi5_pcie_rescal_calibrate(NULL, &out) == RPI5_PCIE_RESCAL_ARGUMENT);
    assert(rpi5_pcie_rescal_calibrate(&session, NULL) == RPI5_PCIE_RESCAL_ARGUMENT);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_rescal_io io = provider(&m);
    assert(rpi5_pcie_rescal_init(NULL, &fdt, &io) == RPI5_PCIE_RESCAL_ARGUMENT);
    assert(rpi5_pcie_rescal_init(&session, NULL, &io) == RPI5_PCIE_RESCAL_ARGUMENT);
    assert(rpi5_pcie_rescal_init(&session, &fdt, NULL) == RPI5_PCIE_RESCAL_ARGUMENT);
    puts("PCIE_RESCAL_HOST_PASS");
    return 0;
}
