/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_DMA_H
#define RPI5_GEM_DMA_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Bounded GEM 64-bit, non-PTP, single-buffer descriptor profile. No MMIO,
 * allocation, address translation, ring scheduling, or implicit barriers. */
#define RPI5_GEM_BUFFER_BYTES 2048u
#define RPI5_GEM_FRAME_MAX 1518u /* One VLAN tag; hardware strips RX FCS. */
struct rpi5_gem_descriptor { uint32_t address, control, address_high, reserved; };
enum rpi5_gem_result {
    RPI5_GEM_OK = 0, RPI5_GEM_PENDING = 1, RPI5_GEM_DROP = 2,
    RPI5_GEM_INVALID = -1, RPI5_GEM_STATE = -2, RPI5_GEM_FAULT = -3
};
enum rpi5_gem_direction { RPI5_GEM_TX = 1, RPI5_GEM_RX = 2 };
enum rpi5_gem_state { RPI5_GEM_FREE, RPI5_GEM_HELD, RPI5_GEM_DEVICE, RPI5_GEM_QUARANTINED };
enum rpi5_gem_descriptor_memory {
    RPI5_GEM_MEMORY_UNPROVEN, RPI5_GEM_MEMORY_COHERENT, RPI5_GEM_MEMORY_UNCACHED
};
struct rpi5_gem_sync {
    void *context;
    /* Return zero after synchronization of the entire isolated packet buffer.
     * for_device=1 prepares DMA; 0 finishes it. TX is device-read, RX device-write.
     * Even a no-op for coherent packets must be an explicit provider decision. */
    int (*packet)(void *, void *, uint64_t, size_t, enum rpi5_gem_direction, int for_device);
    void (*release)(void *); /* CPU writes visible before handing ownership to DMA. */
    void (*acquire)(void *); /* DMA writes visible after observing CPU ownership. */
};
struct rpi5_gem_slot {
    volatile struct rpi5_gem_descriptor *descriptor;
    void *buffer;
    uint64_t dma_address, generation;
    struct rpi5_gem_sync sync;
    uint32_t wrap, length;
    enum rpi5_gem_direction direction;
    enum rpi5_gem_state state;
};
struct rpi5_gem_lease { const struct rpi5_gem_slot *owner; uint64_t generation; };
struct rpi5_gem_packet {
    struct rpi5_gem_lease lease;
    void *buffer; /* NULL for dropped RX frames; never exposed while DMA-owned. */
    uint32_t length, control;
};

/* Caller serializes all operations, forbids callback reentry, and retains the
 * slot/descriptor/mapping for its entire lifetime. Init is only legal with the
 * channel independently proven quiescent and no outstanding leases. It is NOT
 * a reset/recovery operation. Mapping addresses must come from a DMA provider,
 * not casts of CPU pointers. Descriptor storage must be provider-proven coherent
 * or uncached: cleaning packed descriptors can corrupt adjacent DMA updates.
 * Packet allocation is exactly 2048 bytes, cache-line isolated at granule 64..256.
 * The MAC adapter must configure ADDR64, no timestamp extensions, zero RX offset,
 * no jumbo/chaining/offloads, RX FCS stripping/bad-FCS rejection, TX padding/FCS.
 * A lease forbids packet access after submit/recycle. Do not reinitialize to
 * evade quarantine or free mappings merely because a timeout expired. */
int rpi5_gem_slot_init(struct rpi5_gem_slot *, volatile struct rpi5_gem_descriptor *,
    enum rpi5_gem_descriptor_memory, void *buffer, uint64_t dma_address,
    uint32_t cache_granule, enum rpi5_gem_direction, int wrap,
    const struct rpi5_gem_sync *);
int rpi5_gem_tx_reserve(struct rpi5_gem_slot *, struct rpi5_gem_packet *);
int rpi5_gem_tx_cancel(struct rpi5_gem_slot *, struct rpi5_gem_lease);
int rpi5_gem_tx_submit(struct rpi5_gem_slot *, struct rpi5_gem_lease, uint32_t length);
/* TX completion returns raw control status, not a promise of wire delivery.
 * All completions release the slot; adapter must interpret variant error bits. */
int rpi5_gem_tx_complete(struct rpi5_gem_slot *, uint32_t *control);
int rpi5_gem_rx_post(struct rpi5_gem_slot *);
/* DROP still returns a lease that must be recycled. Packet buffer is NULL. */
int rpi5_gem_rx_complete(struct rpi5_gem_slot *, struct rpi5_gem_packet *);
int rpi5_gem_rx_recycle(struct rpi5_gem_slot *, struct rpi5_gem_lease);
#ifdef __cplusplus
}
#endif
#endif
