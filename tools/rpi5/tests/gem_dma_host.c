/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_dma.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(256) unsigned char buffer[2048];
static _Alignas(16) struct rpi5_gem_descriptor descriptor;
static struct rpi5_gem_slot slot;
static unsigned char events[64];
static size_t count;
static int fail_sync;
static const uint64_t dma = UINT64_C(0xabcde123400);

static int owned(void)
{
    return slot.direction == RPI5_GEM_TX ? !!(descriptor.control & UINT32_C(0x80000000))
        : !!(descriptor.address & 1);
}

static void event(unsigned char e) { assert(count < sizeof(events)); events[count++] = e; }
static int sync_packet(void *ctx, void *p, uint64_t address, size_t bytes,
    enum rpi5_gem_direction direction, int for_device)
{
    assert(ctx == &count && p == buffer && address == dma && bytes == 2048);
    assert(direction == slot.direction && owned());
    event(for_device ? 'D' : 'C');
    return fail_sync;
}
static void release(void *ctx) { assert(ctx == &count && owned()); event('R'); }
static void acquire(void *ctx) { assert(ctx == &count && owned()); event('A'); }
static struct rpi5_gem_sync ops = { &count, sync_packet, release, acquire };

static void init(enum rpi5_gem_direction direction, int wrap)
{
    memset(&slot, 0, sizeof(slot));
    memset(&descriptor, 0, sizeof(descriptor));
    memset(buffer, 0, sizeof(buffer));
    count = 0;
    fail_sync = 0;
    assert(rpi5_gem_slot_init(&slot, &descriptor, RPI5_GEM_MEMORY_COHERENT,
        buffer, dma, 256, direction, wrap, &ops) == RPI5_GEM_OK);
}
static void expect(const char *s) { assert(count == strlen(s) && !memcmp(events, s, count)); }

static void layout_and_rejections(void)
{
    struct rpi5_gem_slot before;
    struct rpi5_gem_descriptor d;
    struct rpi5_gem_sync missing;
    init(RPI5_GEM_TX, 1);
    assert(descriptor.address == 0xde123400 && descriptor.address_high == 0xabc);
    assert(descriptor.control == 0xc0000000 && descriptor.reserved == 0);
    assert(!memcmp(&descriptor, (unsigned char[]){0,0x34,0x12,0xde,0,0,0,0xc0,
        0xbc,0x0a,0,0,0,0,0,0}, 16));
    before = slot; d = descriptor;
#define INVALID(mem, buf, addr, gran, dir, wrap, sync) \
    assert(rpi5_gem_slot_init(&slot, &descriptor, mem, buf, addr, gran, dir, wrap, sync) == RPI5_GEM_INVALID)
    INVALID(RPI5_GEM_MEMORY_UNPROVEN, buffer, dma, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(99, buffer, dma, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer+1, dma, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma+4, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 32, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 96, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 512, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, UINT64_MAX-63, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, (void *)(UINTPTR_MAX-63), dma, 64, RPI5_GEM_TX, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, 3, 1, &ops);
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, RPI5_GEM_TX, 2, &ops);
    missing = ops; missing.packet = NULL;
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, RPI5_GEM_TX, 1, &missing);
    missing = ops; missing.release = NULL;
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, RPI5_GEM_TX, 1, &missing);
    missing = ops; missing.acquire = NULL;
    INVALID(RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, RPI5_GEM_TX, 1, &missing);
    assert(rpi5_gem_slot_init(&slot, (void *)((char *)&descriptor + 4),
        RPI5_GEM_MEMORY_COHERENT, buffer, dma, 64, RPI5_GEM_TX, 1, &ops) == RPI5_GEM_INVALID);
    assert(rpi5_gem_slot_init(&slot, (void *)buffer, RPI5_GEM_MEMORY_COHERENT,
        buffer, dma, 64, RPI5_GEM_TX, 1, &ops) == RPI5_GEM_INVALID);
    assert(!memcmp(&slot, &before, sizeof(slot)) && !memcmp(&descriptor, &d, 16));
    expect("");
    assert(rpi5_gem_slot_init(&slot, &descriptor, RPI5_GEM_MEMORY_UNCACHED,
        buffer, dma, 64, RPI5_GEM_RX, 0, &ops) == 0);
    assert(descriptor.address == 0xde123401 && descriptor.control == 0);
}

static void tx_lifecycle(void)
{
    struct rpi5_gem_packet packet, untouched, next;
    uint32_t status = 0x12345678;
    init(RPI5_GEM_TX, 1);
    assert(rpi5_gem_tx_reserve(&slot, &packet) == 0);
    assert(packet.buffer == buffer && packet.length == 2048 && packet.lease.generation == 1);
    memset(buffer, 0x5a, 64);
    untouched = packet;
    assert(rpi5_gem_tx_reserve(&slot, &packet) == RPI5_GEM_STATE);
    assert(!memcmp(&packet, &untouched, sizeof(packet)));
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 13) == RPI5_GEM_INVALID);
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 1519) == RPI5_GEM_INVALID);
    assert(rpi5_gem_tx_submit(&slot, (struct rpi5_gem_lease){NULL,1}, 64) == RPI5_GEM_STATE);
    {
        struct rpi5_gem_slot another = slot;
        assert(rpi5_gem_tx_submit(&slot, (struct rpi5_gem_lease){&another,1}, 64) == RPI5_GEM_STATE);
    }
    expect("");
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 64) == 0);
    assert(descriptor.control == 0x40008040 && slot.state == RPI5_GEM_DEVICE);
    expect("DR");
    assert(rpi5_gem_tx_reserve(&slot, &next) == RPI5_GEM_STATE);
    assert(rpi5_gem_tx_cancel(&slot, packet.lease) == RPI5_GEM_STATE);
    assert(rpi5_gem_tx_complete(&slot, &status) == RPI5_GEM_PENDING && status == 0x12345678);
    expect("DR");
    descriptor.control |= UINT32_C(0x80000000) | UINT32_C(0x20000000);
    assert(rpi5_gem_tx_complete(&slot, &status) == 0 && status == 0xe0008040);
    expect("DRAC"); /* Error status retained; not mistaken for wire delivery. */
    assert(rpi5_gem_tx_reserve(&slot, &next) == 0 && next.lease.generation == 2);
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 64) == RPI5_GEM_STATE);
    assert(rpi5_gem_tx_cancel(&slot, next.lease) == 0);
    assert(rpi5_gem_tx_cancel(&slot, next.lease) == RPI5_GEM_STATE);
    slot.generation = UINT64_MAX;
    assert(rpi5_gem_tx_reserve(&slot, &next) == RPI5_GEM_FAULT);
    assert(slot.state == RPI5_GEM_QUARANTINED);
}

static void rx_lifecycle_and_drops(void)
{
    struct rpi5_gem_packet packet, previous;
    const uint32_t bad[] = {0, 13|0xc000, 1519|0xc000, 4095|0xc000,
        64|0x4000, 64|0x8000, 64|0xd000, 64|0xe000};
    init(RPI5_GEM_RX, 1);
    assert(descriptor.address == 0xde123403 && descriptor.control == 0);
    assert(rpi5_gem_rx_post(&slot) == 0 && descriptor.address == 0xde123402);
    assert(rpi5_gem_rx_post(&slot) == RPI5_GEM_STATE);
    memset(&packet, 0x3c, sizeof(packet)); previous = packet;
    assert(rpi5_gem_rx_complete(&slot, &packet) == RPI5_GEM_PENDING);
    assert(!memcmp(&packet, &previous, sizeof(packet))); expect("DR");
    descriptor.control = 0xc000|1518;
    descriptor.address |= 1;
    assert(rpi5_gem_rx_complete(&slot, &packet) == 0);
    assert(packet.length == 1518 && packet.buffer == buffer && packet.lease.generation == 1);
    expect("DRAC");
    previous = packet;
    {
        struct rpi5_gem_slot another = slot;
        assert(rpi5_gem_rx_recycle(&slot, (struct rpi5_gem_lease){&another,1}) == RPI5_GEM_STATE);
    }
    assert(rpi5_gem_rx_recycle(&slot, packet.lease) == 0 && descriptor.control == 0);
    assert(rpi5_gem_rx_recycle(&slot, packet.lease) == RPI5_GEM_STATE);
    expect("DRACDR");
    for (size_t i = 0; i < sizeof(bad)/sizeof(bad[0]); ++i) {
        count = 0;
        descriptor.control = bad[i]; descriptor.address |= 1;
        assert(rpi5_gem_rx_complete(&slot, &packet) == RPI5_GEM_DROP);
        assert(packet.buffer == NULL && packet.length == 0 && packet.control == bad[i]);
        assert(rpi5_gem_rx_recycle(&slot, previous.lease) == RPI5_GEM_STATE);
        assert(rpi5_gem_rx_recycle(&slot, packet.lease) == 0);
        previous = packet; expect("ACDR");
    }
}

static void faults(void)
{
    struct rpi5_gem_packet packet;
    uint32_t status;
    /* Every immutable descriptor word is independently guarded. */
    for (unsigned i = 0; i < 4; ++i) {
        init(RPI5_GEM_TX, 0);
        assert(rpi5_gem_tx_reserve(&slot, &packet) == 0);
        assert(rpi5_gem_tx_submit(&slot, packet.lease, 14) == 0);
        descriptor.control |= 0x80000000;
        if (i == 0) descriptor.address ^= 4;
        if (i == 1) descriptor.control ^= 0x40000000;
        if (i == 2) descriptor.address_high ^= 1;
        if (i == 3) descriptor.reserved = 1;
        assert(rpi5_gem_tx_complete(&slot, &status) == RPI5_GEM_FAULT);
        assert(slot.state == RPI5_GEM_QUARANTINED); expect("DRA");
        assert(rpi5_gem_tx_reserve(&slot, &packet) == RPI5_GEM_STATE);
        init(RPI5_GEM_RX, 0);
        assert(rpi5_gem_rx_post(&slot) == 0);
        descriptor.address |= 1; descriptor.control = 0xc040;
        if (i == 0) descriptor.address ^= 4;
        if (i == 1) descriptor.address ^= 2;
        if (i == 2) descriptor.address_high ^= 1;
        if (i == 3) descriptor.reserved = 1;
        assert(rpi5_gem_rx_complete(&slot, &packet) == RPI5_GEM_FAULT);
        assert(slot.state == RPI5_GEM_QUARANTINED); expect("DRA");
    }
    init(RPI5_GEM_TX, 0);
    descriptor.control = 0;
    assert(rpi5_gem_tx_reserve(&slot, &packet) == RPI5_GEM_FAULT); expect("");
    init(RPI5_GEM_TX, 0);
    assert(rpi5_gem_tx_reserve(&slot, &packet) == 0);
    fail_sync = 1;
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 64) == RPI5_GEM_FAULT);
    assert(owned() && slot.state == RPI5_GEM_QUARANTINED); expect("D");
    init(RPI5_GEM_TX, 0);
    assert(rpi5_gem_tx_reserve(&slot, &packet) == 0);
    assert(rpi5_gem_tx_submit(&slot, packet.lease, 64) == 0);
    descriptor.control |= 0x80000000; fail_sync = 1;
    assert(rpi5_gem_tx_complete(&slot, &status) == RPI5_GEM_FAULT); expect("DRAC");
    init(RPI5_GEM_RX, 0);
    fail_sync = 1;
    assert(rpi5_gem_rx_post(&slot) == RPI5_GEM_FAULT && owned()); expect("D");
    init(RPI5_GEM_RX, 0);
    assert(rpi5_gem_rx_post(&slot) == 0);
    descriptor.address |= 1; descriptor.control = 0xc040; fail_sync = 1;
    assert(rpi5_gem_rx_complete(&slot, &packet) == RPI5_GEM_FAULT); expect("DRAC");
    init(RPI5_GEM_RX, 0);
    assert(rpi5_gem_rx_post(&slot) == 0);
    descriptor.address |= 1; descriptor.control = 0xc040;
    assert(rpi5_gem_rx_complete(&slot, &packet) == 0);
    fail_sync = 1;
    assert(rpi5_gem_rx_recycle(&slot, packet.lease) == RPI5_GEM_FAULT && owned());
    expect("DRACD");
    init(RPI5_GEM_RX, 0);
    assert(rpi5_gem_rx_post(&slot) == 0);
    descriptor.address |= 1; descriptor.control = 0xc040; slot.generation = UINT64_MAX;
    assert(rpi5_gem_rx_complete(&slot, &packet) == RPI5_GEM_FAULT);
    assert(slot.state == RPI5_GEM_QUARANTINED);
}

int main(void)
{
    layout_and_rejections(); tx_lifecycle(); rx_lifecycle_and_drops(); faults();
    puts("GEM_DMA_HOST_PASS");
    return 0;
}
