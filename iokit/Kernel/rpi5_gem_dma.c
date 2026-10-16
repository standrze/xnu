/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_dma.h"
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "GEM descriptor stores require a little-endian target"
#endif
_Static_assert(sizeof(struct rpi5_gem_descriptor) == 16, "64-bit GEM descriptor size");
_Static_assert(offsetof(struct rpi5_gem_descriptor, control) == 4, "control offset");
_Static_assert(offsetof(struct rpi5_gem_descriptor, address_high) == 8, "high offset");
_Static_assert(offsetof(struct rpi5_gem_descriptor, reserved) == 12, "reserved offset");

#define TX_USED UINT32_C(0x80000000)
#define TX_WRAP UINT32_C(0x40000000)
#define TX_LAST UINT32_C(0x00008000)
#define TX_LENGTH UINT32_C(0x00003fff)
#define RX_USED UINT32_C(1)
#define RX_WRAP UINT32_C(2)
#define RX_SOF UINT32_C(0x00004000)
#define RX_EOF UINT32_C(0x00008000)
#define RX_LENGTH UINT32_C(0x00000fff)

static int fault(struct rpi5_gem_slot *s)
{
    s->state = RPI5_GEM_QUARANTINED;
    return RPI5_GEM_FAULT;
}

static int generation(struct rpi5_gem_slot *s)
{
    if (s->generation == UINT64_MAX) return fault(s);
    ++s->generation;
    return RPI5_GEM_OK;
}

static int lease_valid(const struct rpi5_gem_slot *s, struct rpi5_gem_lease lease)
{
    return lease.owner == s && lease.generation != 0 && lease.generation == s->generation;
}

static int packet_sync(struct rpi5_gem_slot *s, int for_device)
{
    if (s->sync.packet(s->sync.context, s->buffer, s->dma_address,
        RPI5_GEM_BUFFER_BYTES, s->direction, for_device) != 0) return fault(s);
    return RPI5_GEM_OK;
}

static uint32_t rx_address(const struct rpi5_gem_slot *s)
{
    return (uint32_t)s->dma_address | (s->wrap ? RX_WRAP : 0);
}

/* Invoke only while CPU-owned, after acquiring completion visibility. */
static int descriptor_valid(const struct rpi5_gem_slot *s)
{
    const volatile struct rpi5_gem_descriptor *d = s->descriptor;
    uint32_t address = d->address;
    if (s->direction == RPI5_GEM_RX) address &= ~RX_USED;
    return address == (s->direction == RPI5_GEM_RX ? rx_address(s) : (uint32_t)s->dma_address)
        && d->address_high == (uint32_t)(s->dma_address >> 32) && d->reserved == 0;
}

int rpi5_gem_slot_init(struct rpi5_gem_slot *s, volatile struct rpi5_gem_descriptor *d,
    enum rpi5_gem_descriptor_memory memory, void *buffer, uint64_t dma,
    uint32_t granule, enum rpi5_gem_direction direction, int wrap,
    const struct rpi5_gem_sync *sync)
{
    uintptr_t b = (uintptr_t)buffer, desc = (uintptr_t)d;
    if (!s || !d || !buffer || !sync || !sync->packet || !sync->release || !sync->acquire
        || (memory != RPI5_GEM_MEMORY_COHERENT && memory != RPI5_GEM_MEMORY_UNCACHED)
        || (direction != RPI5_GEM_TX && direction != RPI5_GEM_RX) || (wrap != 0 && wrap != 1)
        || granule < 64 || granule > 256 || (granule & (granule - 1))
        || (desc & 15) || (b & (granule - 1)) || (dma & (granule - 1))
        || b > UINTPTR_MAX - (RPI5_GEM_BUFFER_BYTES - 1)
        || dma > UINT64_MAX - (RPI5_GEM_BUFFER_BYTES - 1) || desc > UINTPTR_MAX - 15
        || (desc <= b + RPI5_GEM_BUFFER_BYTES - 1 && b <= desc + 15)) return RPI5_GEM_INVALID;
    s->descriptor = d;
    s->buffer = buffer;
    s->dma_address = dma;
    s->generation = 0;
    s->sync = *sync;
    s->wrap = (uint32_t)wrap;
    s->length = 0;
    s->direction = direction;
    s->state = RPI5_GEM_FREE;
    d->address = direction == RPI5_GEM_RX ? rx_address(s) | RX_USED : (uint32_t)dma;
    d->control = direction == RPI5_GEM_TX ? TX_USED | (wrap ? TX_WRAP : 0) : 0;
    d->address_high = (uint32_t)(dma >> 32);
    d->reserved = 0;
    return RPI5_GEM_OK;
}

int rpi5_gem_tx_reserve(struct rpi5_gem_slot *s, struct rpi5_gem_packet *out)
{
    if (!s || !out || s->direction != RPI5_GEM_TX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_FREE) return RPI5_GEM_STATE;
    if (!(s->descriptor->control & TX_USED) || !descriptor_valid(s)
        || (s->descriptor->control & TX_WRAP) != (s->wrap ? TX_WRAP : 0)) return fault(s);
    if (generation(s)) return RPI5_GEM_FAULT;
    s->state = RPI5_GEM_HELD;
    *out = (struct rpi5_gem_packet){ {s, s->generation}, s->buffer, RPI5_GEM_BUFFER_BYTES, 0 };
    return RPI5_GEM_OK;
}

int rpi5_gem_tx_cancel(struct rpi5_gem_slot *s, struct rpi5_gem_lease lease)
{
    if (!s || s->direction != RPI5_GEM_TX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_HELD || !lease_valid(s, lease)) return RPI5_GEM_STATE;
    s->state = RPI5_GEM_FREE;
    return RPI5_GEM_OK;
}

int rpi5_gem_tx_submit(struct rpi5_gem_slot *s, struct rpi5_gem_lease lease, uint32_t length)
{
    if (!s || s->direction != RPI5_GEM_TX || length < 14 || length > RPI5_GEM_FRAME_MAX)
        return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_HELD || !lease_valid(s, lease)) return RPI5_GEM_STATE;
    if (!(s->descriptor->control & TX_USED) || !descriptor_valid(s)
        || (s->descriptor->control & TX_WRAP) != (s->wrap ? TX_WRAP : 0)) return fault(s);
    if (packet_sync(s, 1)) return RPI5_GEM_FAULT;
    s->length = length;
    s->state = RPI5_GEM_DEVICE;
    s->sync.release(s->sync.context);
    /* One aligned ownership store; do not expose an intermediate control word. */
    s->descriptor->control = (s->wrap ? TX_WRAP : 0) | TX_LAST | length;
    return RPI5_GEM_OK;
}

int rpi5_gem_tx_complete(struct rpi5_gem_slot *s, uint32_t *control)
{
    uint32_t status;
    if (!s || !control || s->direction != RPI5_GEM_TX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_DEVICE) return RPI5_GEM_STATE;
    if (!(s->descriptor->control & TX_USED)) return RPI5_GEM_PENDING;
    s->sync.acquire(s->sync.context);
    status = s->descriptor->control;
    if (!descriptor_valid(s) || !(status & TX_USED)
        || (status & TX_WRAP) != (s->wrap ? TX_WRAP : 0)
        || (status & (TX_LENGTH | TX_LAST | UINT32_C(0x10000))) != (s->length | TX_LAST))
        return fault(s);
    if (packet_sync(s, 0)) return RPI5_GEM_FAULT;
    s->state = RPI5_GEM_FREE;
    *control = status;
    return RPI5_GEM_OK;
}

static int rx_publish(struct rpi5_gem_slot *s)
{
    if (!(s->descriptor->address & RX_USED) || !descriptor_valid(s)) return fault(s);
    if (packet_sync(s, 1)) return RPI5_GEM_FAULT;
    s->descriptor->control = 0;
    s->state = RPI5_GEM_DEVICE;
    s->sync.release(s->sync.context);
    s->descriptor->address = rx_address(s);
    return RPI5_GEM_OK;
}

int rpi5_gem_rx_post(struct rpi5_gem_slot *s)
{
    if (!s || s->direction != RPI5_GEM_RX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_FREE) return RPI5_GEM_STATE;
    return rx_publish(s);
}

int rpi5_gem_rx_complete(struct rpi5_gem_slot *s, struct rpi5_gem_packet *out)
{
    uint32_t status, length;
    int valid;
    if (!s || !out || s->direction != RPI5_GEM_RX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_DEVICE) return RPI5_GEM_STATE;
    if (!(s->descriptor->address & RX_USED)) return RPI5_GEM_PENDING;
    s->sync.acquire(s->sync.context);
    status = s->descriptor->control;
    if (!(s->descriptor->address & RX_USED) || !descriptor_valid(s)) return fault(s);
    if (packet_sync(s, 0) || generation(s)) return RPI5_GEM_FAULT;
    length = status & RX_LENGTH;
    valid = (status & (RX_SOF | RX_EOF)) == (RX_SOF | RX_EOF)
        && (status & UINT32_C(0x00003000)) == 0 /* RX offset must remain zero. */
        && length >= 14 && length <= RPI5_GEM_FRAME_MAX;
    s->state = RPI5_GEM_HELD;
    *out = (struct rpi5_gem_packet){ {s, s->generation}, valid ? s->buffer : NULL,
        valid ? length : 0, status };
    return valid ? RPI5_GEM_OK : RPI5_GEM_DROP;
}

int rpi5_gem_rx_recycle(struct rpi5_gem_slot *s, struct rpi5_gem_lease lease)
{
    if (!s || s->direction != RPI5_GEM_RX) return RPI5_GEM_INVALID;
    if (s->state != RPI5_GEM_HELD || !lease_valid(s, lease)) return RPI5_GEM_STATE;
    return rx_publish(s);
}
