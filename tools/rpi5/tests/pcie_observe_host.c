/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_observe.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    unsigned calls, fail_call, selected, ordered, reads, link_reads;
    unsigned drop_at, changed_word;
    uint32_t status, selector, change_mask;
    uint32_t header[16];
};

static int fail(struct model *m)
{
    return ++m->calls == m->fail_call;
}

static int read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *m = context;
    if (fail(m)) return -1;
    if (offset == 0x4068) {
        m->link_reads++;
        *value = m->link_reads == m->drop_at ? 0 : m->status;
    } else if (offset == 0x9000) {
        assert(m->selected && m->ordered && !m->reads);
        *value = m->selector;
    } else {
        assert(offset >= 0x8000 && offset < 0x8040 && !(offset & 3));
        assert(m->selected && m->ordered);
        unsigned word = (offset - 0x8000) / 4;
        assert(word == m->reads % 16);
        assert(m->link_reads == m->reads + 2);
        *value = m->header[word];
        if (m->reads >= 16 && word == m->changed_word) *value ^= m->change_mask;
        m->reads++;
    }
    return 0;
}

static int select_rp1(void *context)
{
    struct model *m = context;
    assert(m->link_reads == 1 && !m->selected && !m->reads);
    if (fail(m)) return -1;
    m->selected++;
    return 0;
}

static int order(void *context)
{
    struct model *m = context;
    assert(m->selected && !m->ordered && !m->reads);
    if (fail(m)) return -1;
    m->ordered++;
    return 0;
}

static struct model fresh(void)
{
    /* Resource-bearing fields of the saved 2026-10-12 Linux header. Link
     * state and callback behavior are synthetic, not Linux or XNU evidence. */
    struct model m = {.status = 0xb0, .selector = 0x00100000,
        .changed_word = 99, .header = {
            0x00011de4, 0x00100406, 0x02000000, 0,
            0x00410000, 0, 0x00400000, 0, 0, 0, 0, 0,
            0, 0x00000040, 0, 0x0000012c
        }};
    return m;
}

static struct rpi5_pcie_observe_io io_for(struct model *m)
{
    struct rpi5_pcie_observe_io io = {
        m, 0x9310, read32, select_rp1, order
    };
    return io;
}

static void rejected(struct model *m, int expected)
{
    struct rpi5_pcie_observation out, before;
    memset(&before, 0xa5, sizeof before);
    out = before;
    struct rpi5_pcie_observe_io io = io_for(m);
    assert(rpi5_pcie_observe_rp1(&io, &out) == expected);
    assert(!memcmp(&out, &before, sizeof out));
}

int main(void)
{
    struct model m = fresh();
    struct rpi5_pcie_observe_io io = io_for(&m);
    struct rpi5_pcie_observation out;
    assert(!rpi5_pcie_observe_rp1(&io, &out));
    assert(m.selected == 1 && m.ordered == 1 && m.reads == 32);
    assert(m.link_reads == 34 && m.calls == 69);
    assert(out.status_before == 0xb0 && out.status_after == 0xb0);
    assert(!memcmp(out.config, m.header, sizeof m.header));
    assert(out.memory_decode_enabled == 1 && out.bus_master_enabled == 1);
    assert(out.bar1_pci_base == 0); /* Does not mean unassigned. */

    m = fresh(); m.header[5] = 0x10000000; io = io_for(&m);
    assert(!rpi5_pcie_observe_rp1(&io, &out));
    assert(out.bar1_pci_base == 0x10000000);
    m = fresh(); m.header[1] = 0; io = io_for(&m);
    assert(!rpi5_pcie_observe_rp1(&io, &out));
    assert(!out.memory_decode_enabled && !out.bus_master_enabled);

    /* Every callback can fail; stop exactly there without retry/publication. */
    for (unsigned call = 1; call <= 69; call++) {
        m = fresh(); m.fail_call = call;
        rejected(&m, RPI5_PCIE_OBSERVE_IO);
        assert(m.calls == call);
    }
    const uint32_t states[] = {0, 0x80, 0x90, 0xa0, 0x30, 0xf0, UINT32_MAX};
    for (unsigned i = 0; i < sizeof states / sizeof states[0]; i++) {
        m = fresh(); m.status = states[i];
        rejected(&m, RPI5_PCIE_OBSERVE_LINK);
        assert(m.calls == 1 && !m.selected && !m.reads);
    }
    /* Link loss before each individual config read, and the final check. */
    for (unsigned step = 2; step <= 34; step++) {
        m = fresh(); m.drop_at = step;
        rejected(&m, RPI5_PCIE_OBSERVE_LINK);
        assert(m.reads == step - 2 && m.selected == 1);
    }
    m = fresh(); m.selector = 0;
    rejected(&m, RPI5_PCIE_OBSERVE_SELECTOR);
    assert(!m.reads);

    const unsigned fields[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
    const uint32_t masks[] = {1, 2, 1, 0x00800000, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10};
    for (unsigned i = 0; i < sizeof fields / sizeof fields[0]; i++) {
        m = fresh(); m.changed_word = fields[i]; m.change_mask = masks[i];
        rejected(&m, i == 0 ? RPI5_PCIE_OBSERVE_PROFILE : RPI5_PCIE_OBSERVE_CHANGED);
    }
    /* Volatile PCI status is preserved but not treated as a BAR change. */
    m = fresh(); m.changed_word = 1; m.change_mask = 0x80000000; io = io_for(&m);
    assert(!rpi5_pcie_observe_rp1(&io, &out));
    assert(out.config[1] == (m.header[1] ^ 0x80000000));

    const unsigned bad_fields[] = {0, 0, 2, 3, 4, 4, 5, 5, 6};
    const uint32_t bad_values[] = {UINT32_MAX, 0, 0x01000000, 0x00010000,
        0x00410004, 0x00410001, 4, 8, 0x00400002};
    for (unsigned i = 0; i < sizeof bad_fields / sizeof bad_fields[0]; i++) {
        m = fresh(); m.header[bad_fields[i]] = bad_values[i];
        rejected(&m, RPI5_PCIE_OBSERVE_PROFILE);
        assert(m.reads == 16);
    }

    m = fresh(); io = io_for(&m);
    memset(&out, 0xa5, sizeof out);
    struct rpi5_pcie_observation before = out;
    assert(rpi5_pcie_observe_rp1(0, &out) == RPI5_PCIE_OBSERVE_ARGUMENT);
    assert(rpi5_pcie_observe_rp1(&io, 0) == RPI5_PCIE_OBSERVE_ARGUMENT);
    io.mapped_bytes = 0x9003;
    assert(rpi5_pcie_observe_rp1(&io, &out) == RPI5_PCIE_OBSERVE_ARGUMENT);
    io = io_for(&m); io.read32 = 0;
    assert(rpi5_pcie_observe_rp1(&io, &out) == RPI5_PCIE_OBSERVE_ARGUMENT);
    io = io_for(&m); io.select_rp1 = 0;
    assert(rpi5_pcie_observe_rp1(&io, &out) == RPI5_PCIE_OBSERVE_ARGUMENT);
    io = io_for(&m); io.order = 0;
    assert(rpi5_pcie_observe_rp1(&io, &out) == RPI5_PCIE_OBSERVE_ARGUMENT);
    assert(m.calls == 0 && !memcmp(&out, &before, sizeof out));
    puts("PCIE_OBSERVE_HOST_PASS");
    return 0;
}
