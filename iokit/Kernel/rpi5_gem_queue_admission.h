/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_QUEUE_ADMISSION_H
#define RPI5_GEM_QUEUE_ADMISSION_H

#include <stdbool.h>
#include "rpi5_gem_ring_stage.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Smallest post-ring hardware boundary: program and read back queue zero's
 * 64-bit RX/TX descriptor bases while both engines remain disabled, endpoint
 * bus mastering stays off, interrupts stay masked, and then restore every
 * queue register.  Descriptors remain CPU-owned for the entire transaction.
 *
 * This is not packet DMA, an interrupt test, an IONetworkingFamily adapter,
 * link readiness, or Ethernet.  No production owner calls this core.  A
 * future board trial must supply the same-boot owner callbacks and an
 * autonomous reset path before opting in.
 */
#define RPI5_GEM_QUEUE_ADMISSION_VERSION 1u
#define RPI5_GEM_QUEUE_ADMISSION_OPERATIONS 29u
#define RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS 60u
#define RPI5_GEM_QUEUE_ADMISSION_CAP_WORDS 8u
#define RPI5_GEM_QUEUE_ADMISSION_RING_CALLBACKS 81u
#define RPI5_GEM_QUEUE_ADMISSION_RING_CURRENT_CHECKS 164u

enum rpi5_gem_queue_admission_state {
	RPI5_GEM_QUEUE_ADMISSION_UNUSED = 0,
	RPI5_GEM_QUEUE_ADMISSION_CHECKING,
	RPI5_GEM_QUEUE_ADMISSION_QUEUES_STAGED,
	RPI5_GEM_QUEUE_ADMISSION_RESTORING,
	RPI5_GEM_QUEUE_ADMISSION_COMPLETE,
	RPI5_GEM_QUEUE_ADMISSION_QUARANTINED
};

enum rpi5_gem_queue_admission_operation {
	RPI5_GEM_QUEUE_ADMISSION_NONE = 0,
	RPI5_GEM_QUEUE_ADMISSION_RING_CHECK,
	RPI5_GEM_QUEUE_ADMISSION_READ32,
	RPI5_GEM_QUEUE_ADMISSION_WRITE32
};

struct rpi5_gem_queue_admission_request {
	const void *owner;
	const void *mapping_provider;
	const void *capability_source;
	uint64_t same_boot_cookie;
	uint64_t not_before;
	uint64_t deadline;
	uint32_t raw_capabilities[RPI5_GEM_QUEUE_ADMISSION_CAP_WORDS];
	enum rpi5_gem_descriptor_memory descriptor_memory;
	struct rpi5_gem_stage_observation rings;
	/* Future live-provider prerequisite.  128 isolated 2-KiB packet spans
	 * plus two retained 16-KiB ring pages form the exact 0x48000 provider.
	 * This core does not allocate, inspect or publish those packet spans. */
	uint32_t provider_bytes;
	uint32_t packet_spans;
	uint32_t packet_bytes;
	uint32_t packet_mapped_bytes;
	uint32_t packet_spans_cpu_owned;
};

struct rpi5_gem_queue_admission_session;

struct rpi5_gem_queue_admission_io {
	void *context;
	/* Fresh owner/thread/phase, MEM decode, maps, clocks, PHY reset release,
	 * exact GEM identity, ring/packet mappings and COMMAND.BME=0. This callback
	 * does not require link-up and performs no
	 * register access and must bind the exact request to the live session. */
	int (*current)(void *, const struct rpi5_gem_queue_admission_session *,
	    const struct rpi5_gem_queue_admission_request *, uint64_t *now);
	/* Compare all 160 descriptors with their exact CPU-owned values and prove
	 * all 128 required packet spans remain mapped and CPU-owned: none has been
	 * released to the device and no DMA ownership transition has occurred. */
	int (*rings_cpu_owned)(void *,
	    const struct rpi5_gem_queue_admission_session *);
	/* One guarded aligned GEM register access.  access_allowed() must pass. */
	int (*read32)(void *, const struct rpi5_gem_queue_admission_session *,
	    uint32_t offset, uint32_t *value);
	int (*write32)(void *, const struct rpi5_gem_queue_admission_session *,
	    uint32_t offset, uint32_t value);
};

struct rpi5_gem_queue_admission_session {
	const struct rpi5_gem_queue_admission_session *self;
	const struct rpi5_gem_queue_admission_request *request;
	struct rpi5_gem_queue_admission_io io;
	enum rpi5_gem_queue_admission_state state;
	enum rpi5_gem_queue_admission_operation pending;
	uint32_t busy;
	uint32_t operations;
	uint32_t current_checks;
	uint32_t ring_checks;
	uint32_t reads;
	uint32_t writes;
	uint32_t index;
	uint32_t offset;
	uint32_t value;
	uint64_t last;
	int error;
};

struct rpi5_gem_queue_admission_observation {
	uint32_t version;
	uint32_t operations;
	uint32_t current_checks;
	uint32_t ring_checks;
	uint32_t reads;
	uint32_t writes;
	uint32_t bus_master_enabled;
	uint32_t engines_enabled;
	uint32_t dma_ownership_transfers;
	uint32_t interrupts_enabled;
	uint64_t same_boot_cookie;
	uint64_t tx_ring_dma;
	uint64_t rx_ring_dma;
};

bool rpi5_gem_queue_admission_access_allowed(
	const struct rpi5_gem_queue_admission_session *,
	enum rpi5_gem_queue_admission_operation, uint32_t offset,
	uint32_t value);

/*
 * The session must be zero and all arguments stable and disjoint.  Any
 * admitted failure quarantines the session.  In particular, failure after
 * a queue-register write does not attempt untrusted compensating I/O; the
 * enclosing trial must park for its already-proven autonomous reset. Success
 * guarantees BME remained off,
 * original queue registers restored, engines never enabled, and descriptors
 * still CPU-owned.  It grants no authority to publish a packet descriptor.
 */
int rpi5_gem_queue_admission_run(
	struct rpi5_gem_queue_admission_session *,
	const struct rpi5_gem_queue_admission_request *,
	const struct rpi5_gem_queue_admission_io *,
	struct rpi5_gem_queue_admission_observation *);

#ifdef __cplusplus
}
#endif
#endif
