/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_RING_STAGE_H
#define RPI5_GEM_RING_STAGE_H
#include "rpi5_gem_dma.h"
#ifdef __cplusplus
extern "C" {
#endif

/* Software-only staging, NOT GEM queue activation. The64-entry minimum from
 * Linux's actual ring policy, plus a conservative sixteen-descriptor tail.
 * RP1's Linux config does not set BD_RD_PREFETCH; padding uses its observed
 * DCFG10 code4 formula, not a claim that its Linux driver allocates the tail.
 * Wire format is64-bit non-PTP; this core does not prove hardware activation. */
#define RPI5_GEM_STAGE_SLOTS 64u
#define RPI5_GEM_STAGE_TAIL_BYTES 256u
#define RPI5_GEM_STAGE_RING_BYTES 1280u
#define RPI5_GEM_STAGE_WORDS 320u
#define RPI5_GEM_STAGE_IO_LIMIT 1281u
#define RPI5_GEM_STAGE_CURRENT_LIMIT 2564u
enum rpi5_gem_stage_state {
    RPI5_GEM_STAGE_UNUSED, RPI5_GEM_STAGE_BUILDING,
    RPI5_GEM_STAGE_HELD, RPI5_GEM_STAGE_QUARANTINED
};
enum rpi5_gem_stage_operation { RPI5_GEM_STAGE_NONE, RPI5_GEM_STAGE_WRITE,
    RPI5_GEM_STAGE_BARRIER, RPI5_GEM_STAGE_READ };
struct rpi5_gem_stage_span { void *cpu; uint64_t dma; size_t bytes; };
struct rpi5_gem_stage_request {
    /* These identities/generation have no authority alone. current() must bind
     * these exact objects to a live driver session and mapping provider. */
    const void *owner, *mapping_provider, *capability_source;
    uint64_t generation, not_before, deadline;
    uint32_t raw_capabilities[8]; /* MID, DCFG1/2/5/6/8/10/12. */
    enum rpi5_gem_descriptor_memory descriptor_memory;
    uint32_t packet_granule;
    struct rpi5_gem_stage_span ring[2], packet[2][RPI5_GEM_STAGE_SLOTS];
};
struct rpi5_gem_stage_session {
    const struct rpi5_gem_stage_session *self;
    const struct rpi5_gem_stage_request *request;
    enum rpi5_gem_stage_state state;
    enum rpi5_gem_stage_operation pending;
    uint32_t busy, callbacks, current_checks, writes_attempted, writes_completed;
    uint32_t reads_completed, ring, offset, value;
    uint64_t last;
    int error;
};
struct rpi5_gem_stage_io {
    void *context;
    /* Bounded, non-reentrant, no state mutation. Return fresh monotonic ticks.
     * Before AND after each operation, prove exact same boot/thread/phase,
     * sole CPU ownership, no DMA/queue publication/outstanding device access,
     * the same live validated capabilities, and all130 retained mappings, CPU
     * aliases/cache policy, device address translations and inbound aperture.
     * Neither a receipt, DAW64, a CPU pointer cast nor a boolean bypass is proof.
     * Provider revocation/concurrent DMA must be excluded for the whole run.
     * Empty/FREE flags alone cannot prove quiescence. */
    int (*current)(void *, const struct rpi5_gem_stage_session *,
        const struct rpi5_gem_stage_request *, uint64_t *now);
    /* CPU descriptor RAM only, never MMIO. Exactly one aligned LE32 access.
     * The callback must verify access_allowed and the actual retained mapping.
     * Partial/failed post-access writes remain attempted side effects. */
    int (*write32)(void *, const struct rpi5_gem_stage_session *, unsigned ring,
        uint32_t offset, uint32_t value);
    int (*read32)(void *, const struct rpi5_gem_stage_session *, unsigned ring,
        uint32_t offset, uint32_t *value);
    /* Provider's explicit descriptor-memory release/order boundary, e.g. the
     * appropriate ARM outer-shareable DMA barrier. Not a packet-cache sync.
     * Packed descriptors must be coherent or uncached, never line-cleaned
     * while another descriptor might be device-owned. No queue-register write. */
    int (*barrier)(void *, const struct rpi5_gem_stage_session *);
};
struct rpi5_gem_stage_observation {
    uint64_t ring_dma[2], generation;
    uint32_t ring_bytes, descriptor_bytes, real_slots, prefetch_bytes;
    uint32_t cpu_owned_descriptors, writes, reads, callbacks, current_checks;
};
int rpi5_gem_ring_stage_access_allowed(const struct rpi5_gem_stage_session *,
    enum rpi5_gem_stage_operation, unsigned ring, uint32_t offset, uint32_t value);
/* All objects and130 CPU/DMA extents disjoint and retained; zero unused
 * session, caller serializes access. No allocation, translation, packet reads
 * or writes, IRQ, MMIO, queue address publication, or descriptor release to DMA.
 * Both complete1280-byte ring allocations must stay inside one4GiB DMA window
 * each; RX/TX may use different high32 bits. All80 descriptors per ring remain
 * CPU-owned, including inert prefetch tails; only slot63 has WRAP.
 * Any admitted failure quarantines storage; no rollback/unmap/free/retry.
 * Caller must retain mappings until independent reset/quiescence proves safe.
 * Success publishes geometry only, never permission to enable DMA. A later
 * driver must separately configure ADDR64/non-PTP/endian/RX framing, packet
 * synchronization, queue ownership, inbound windows and interrupts.
 * Future Apple adapter: retain IOBufferMemoryDescriptor plus prepared genuine
 * IODMACommand mappings and gen64IOVMSegments results for the whole lifetime;
 * prepare/complete/allocation are NOT legal under the existing IRQ-off owner.
 * No such provider or physical DMA proof is implemented by this pure core. */
int rpi5_gem_ring_stage(struct rpi5_gem_stage_session *,
    const struct rpi5_gem_stage_request *, const struct rpi5_gem_stage_io *,
    struct rpi5_gem_stage_observation *);
#ifdef __cplusplus
}
#endif
#endif
