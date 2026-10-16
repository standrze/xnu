/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_CONTRACT_H
#define RPI5_SD_CONTRACT_H
#include <stddef.h>
#include <stdint.h>
#include "rpi5_sd_handoff.h"
struct rpi5_sd_binding {
    uint64_t base[5];
    uint32_t size[5], variant, source_hz, settling_us;
};
/* Native Apple DT properties, explicitly little endian. No aliases, bus
 * inference, MMIO, pin control or ownership claim. Output atomic on failure. */
int rpi5_sd_binding_decode(const void *host, size_t host_bytes,
    const void *power, size_t power_bytes, const void *variant, size_t variant_bytes,
    const void *clock, size_t clock_bytes, const void *settle, size_t settle_bytes,
    const void *irq, size_t irq_bytes, struct rpi5_sd_binding *);
#define RPI5_SD_MAX_READ_BLOCKS 32u
#define RPI5_SD_MAX_REQUESTS 32u
int rpi5_sd_read_request_valid(uint64_t sectors, uint64_t block, uint64_t count, uint64_t bytes);
/* Intrusive single-consumer queue. The kernel caller supplies one mutex for
 * every operation, retains requests/descriptors, and completes outside it.
 * Closing rejects new submissions but preserves queued requests for cancellation.
 */
struct rpi5_sd_request_link { struct rpi5_sd_request_link *next; };
struct rpi5_sd_request_queue {
    struct rpi5_sd_request_link *head, *tail;
    uint32_t queued, active, accepting;
};
int rpi5_sd_queue_push(struct rpi5_sd_request_queue *, struct rpi5_sd_request_link *);
struct rpi5_sd_request_link *rpi5_sd_queue_pop(struct rpi5_sd_request_queue *);
int rpi5_sd_queue_complete(struct rpi5_sd_request_queue *);
#endif
