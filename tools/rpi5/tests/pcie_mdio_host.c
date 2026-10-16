/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_mdio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_mdio *session;
    unsigned calls, fail_at, all_ones_at, polls, ready_at, writes, clocks;
    unsigned backwards_at, delay_elapsed, read_latency;
    uint32_t command, written_data, idle;
    uint64_t now;
    int reading, stopped_clock, different_address_readback;
    char trace[80];
};
static int step(struct model *m, char operation)
{
    assert(m->session->state == RPI5_PCIE_MDIO_BUSY);
    assert(m->calls < sizeof m->trace);
    m->trace[m->calls++] = operation;
    struct rpi5_pcie_mdio_observation out;
    assert(rpi5_pcie_mdio_read(m->session, 0, &out) == RPI5_PCIE_MDIO_STATE);
    assert(rpi5_pcie_mdio_write(m->session, 0, 0, &out) == RPI5_PCIE_MDIO_STATE);
    return m->calls == m->fail_at;
}
static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    int initial = m->session->completed_callbacks == 0;
    assert(offset == 0x1100 || offset == 0x1104 || offset == 0x1108);
    if (step(m, initial ? 'I' : offset == 0x1100 ? 'C' : m->reading ? 'R' : 'B')) return -1;
    if (initial) {
        assert(offset == 0x1104); *value = m->idle;
    } else if (offset == 0x1100) {
        *value = m->command ^ (m->different_address_readback ? 0x40 : 0);
    } else {
        assert(offset == (m->reading ? 0x1108 : 0x1104));
        m->polls++;
        if (!m->stopped_clock) m->now += m->read_latency;
        unsigned done = m->polls >= m->ready_at;
        *value = m->reading ? 0x123456 | (done ? 0x80000000u : 0) :
            (m->written_data & 0xffff) | (done ? 0 : 0x80000000u);
    }
    if (m->calls == m->all_ones_at) *value = UINT32_MAX;
    return 0;
}
static int write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m = context;
    assert(offset == 0x1100 || offset == 0x1104);
    int failed = step(m, offset == 0x1100 ? 'A' : 'W');
    m->writes++;
    if (offset == 0x1100) {
        assert(value == ((m->reading ? 0x100000u : 0) | 0x1f));
        m->command = value;
    } else {
        assert(!m->reading && value == 0x800050b9u);
        m->written_data = value;
    }
    return failed ? -1 : 0; /* failure may follow a completed write */
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
static int delay_us(void *context, uint32_t value)
{
    struct model *m = context;
    assert(value == 10);
    if (step(m, 'D')) return -1;
    if (!m->stopped_clock) m->now += m->delay_elapsed;
    return 0;
}
static struct rpi5_pcie_fdt topology(void)
{
    struct rpi5_pcie_fdt fdt = {0};
    fdt.bridge_regs = (struct rpi5_range){0x1000120000, 0x1000129310};
    return fdt;
}
static struct rpi5_pcie_mdio_io provider(struct model *m)
{
    struct rpi5_pcie_mdio_io io = {
        m, 0x1000120000, 0x9310, read32, write32, order, now_us, delay_us
    };
    return io;
}
static void prepare(struct model *m, struct rpi5_pcie_mdio *session, int reading)
{
    memset(m, 0, sizeof *m); memset(session, 0, sizeof *session);
    m->session = session; m->reading = reading; m->ready_at = 1;
    m->now = 10000; m->delay_elapsed = 10;
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_mdio_io io = provider(m);
    assert(!rpi5_pcie_mdio_init(session, &fdt, &io));
    assert(!m->calls && session->state == RPI5_PCIE_MDIO_READY);
}
static int execute(struct model *m, struct rpi5_pcie_mdio_observation *out)
{
    return m->reading ? rpi5_pcie_mdio_read(m->session, 31, out) :
        rpi5_pcie_mdio_write(m->session, 31, 0x50b9, out);
}
static void rejects(struct model *m, int rc)
{
    struct rpi5_pcie_mdio_observation out, before;
    memset(&out, 0xa5, sizeof out); before = out;
    assert(execute(m, &out) == rc);
    assert(!memcmp(&out, &before, sizeof out));
    assert(m->session->state == RPI5_PCIE_MDIO_QUARANTINED);
    unsigned calls = m->calls;
    assert(execute(m, &out) == RPI5_PCIE_MDIO_STATE);
    struct rpi5_pcie_fdt fdt = topology();
    struct rpi5_pcie_mdio_io io = provider(m);
    assert(rpi5_pcie_mdio_init(m->session, &fdt, &io) == RPI5_PCIE_MDIO_STATE);
    assert(calls == m->calls);
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_mdio session;
    struct rpi5_pcie_mdio_observation out;
    for (int reading = 0; reading < 2; reading++) {
        for (unsigned ready = 1; ready <= 11; ready++) {
            prepare(&m, &session, reading); m.ready_at = ready;
            assert(!execute(&m, &out));
            assert(out.poll_reads == ready && out.poll_elapsed_us == 10 * (ready - 1));
            assert(out.payload == (reading ? 0x123456 : 0x50b9));
            assert(out.command == ((reading ? 0x100000u : 0) | 0x1f));
            assert(m.calls == (reading ? 7u : 9u) + 4 * (ready - 1));
            assert(m.writes == (reading ? 1u : 2u));
            assert(session.state == RPI5_PCIE_MDIO_READY && session.completed_callbacks == m.calls);
            unsigned total = m.calls;
            for (unsigned fail = 1; fail <= total; fail++) {
                prepare(&m, &session, reading); m.ready_at = ready; m.fail_at = fail;
                rejects(&m, RPI5_PCIE_MDIO_IO);
                assert(m.calls == fail && session.completed_callbacks == fail - 1);
            }
        }
        prepare(&m, &session, reading);
        assert(!execute(&m, &out));
        assert(!memcmp(m.trace, reading ? "IAOCTRT" : "IAOCWOTBT", m.calls));
        /* Successful transactions are reusable; init is not. */
        m.calls = m.polls = m.clocks = m.writes = 0;
        assert(!execute(&m, &out));
        const unsigned bad_reads[] = {1, 4, reading ? 6u : 8u};
        for (unsigned i = 0; i < 3; i++) {
            prepare(&m, &session, reading); m.all_ones_at = bad_reads[i];
            rejects(&m, RPI5_PCIE_MDIO_READBACK);
            assert(m.calls == bad_reads[i]);
        }
        prepare(&m, &session, reading); m.idle = 0x80000000;
        rejects(&m, RPI5_PCIE_MDIO_ALREADY_BUSY);
        assert(m.calls == 1 && !m.writes);
        prepare(&m, &session, reading); m.ready_at = 12;
        rejects(&m, RPI5_PCIE_MDIO_TIMEOUT);
        assert(m.polls == 11 && m.writes == (reading ? 1u : 2u));
        prepare(&m, &session, reading); m.read_latency = 101;
        rejects(&m, RPI5_PCIE_MDIO_TIMEOUT); /* late completion is failure */
        assert(m.polls == 1);
        prepare(&m, &session, reading); m.ready_at = 2; m.delay_elapsed = 101;
        rejects(&m, RPI5_PCIE_MDIO_TIMEOUT); assert(m.polls == 1);
        prepare(&m, &session, reading); m.backwards_at = 2;
        rejects(&m, RPI5_PCIE_MDIO_CLOCK);
        prepare(&m, &session, reading); m.ready_at = 2; m.delay_elapsed = 0; m.backwards_at = 3;
        rejects(&m, RPI5_PCIE_MDIO_CLOCK);
        prepare(&m, &session, reading); m.stopped_clock = 1; m.ready_at = 12;
        rejects(&m, RPI5_PCIE_MDIO_TIMEOUT); assert(m.polls == 11);
        prepare(&m, &session, reading); m.different_address_readback = 1;
        assert(!execute(&m, &out)); /* reference readback is a flush, not equality */
    }
    for (unsigned bad = 0; bad < 9; bad++) {
        prepare(&m, &session, 0); memset(&session, 0, sizeof session);
        struct rpi5_pcie_mdio before = session;
        struct rpi5_pcie_fdt fdt = topology();
        struct rpi5_pcie_mdio_io io = provider(&m);
        switch (bad) {
            case 0: io.read32 = NULL; break;
            case 1: io.write32 = NULL; break;
            case 2: io.order = NULL; break;
            case 3: io.now_us = NULL; break;
            case 4: io.delay_us = NULL; break;
            case 5: io.physical_base++; break;
            case 6: io.mapped_bytes--; break;
            case 7: fdt.bridge_regs.start++; break;
            case 8: fdt.bridge_regs.end++; break;
        }
        assert(rpi5_pcie_mdio_init(&session, &fdt, &io) == RPI5_PCIE_MDIO_ARGUMENT);
        assert(!m.calls && !memcmp(&session, &before, sizeof session));
    }
    prepare(&m, &session, 0);
    assert(rpi5_pcie_mdio_read(&session, 32, &out) == RPI5_PCIE_MDIO_ARGUMENT);
    assert(rpi5_pcie_mdio_write(&session, 255, 0, &out) == RPI5_PCIE_MDIO_ARGUMENT);
    assert(rpi5_pcie_mdio_write(&session, 0, 0, NULL) == RPI5_PCIE_MDIO_ARGUMENT);
    assert(rpi5_pcie_mdio_read(NULL, 0, &out) == RPI5_PCIE_MDIO_ARGUMENT);
    assert(!m.calls && session.state == RPI5_PCIE_MDIO_READY);
    puts("PCIE_MDIO_HOST_PASS");
    return 0;
}
