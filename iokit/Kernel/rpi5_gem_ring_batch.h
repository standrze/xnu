/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_RING_BATCH_H
#define RPI5_GEM_RING_BATCH_H
#include "rpi5_gem_ring_stage.h"
#ifdef __cplusplus
extern "C" {
#endif
#define RPI5_GEM_BATCH_BYTES 64u
#define RPI5_GEM_BATCH_WORDS 16u
#define RPI5_GEM_BATCH_IO_LIMIT 81u
#define RPI5_GEM_BATCH_CURRENT_LIMIT 164u
/* Same exact64TX+64RX descriptor/prefetch geometry as the frozen word codec.
 * All slots remain CPU-owned. This is CPU RAM initialization only, not device
 * ownership publication, a cache-maintenance operation or DMA activation.
 * Each fixed64-byte access has fresh owner/time checks before and after.
 * The callback must perform the whole bounded access without any intervening
 * callback, allocation, MMIO or external call. Caller excludes concurrent
 * writes/revocation; a fault/exception is terminal, never a resumable retry. */
struct rpi5_gem_batch_io {
    void *context;
    int (*current)(void *,const struct rpi5_gem_stage_session *,const struct rpi5_gem_stage_request *,uint64_t *);
    /* Write exactly16 words, four descriptors in upper/reserved/control/lower
     * order. A nonzero callback may have partially changed the whole64B.
     * No completed-word claim is made for that batch. */
    int (*write64)(void *,const struct rpi5_gem_stage_session *,unsigned,uint32_t,const uint32_t [16]);
    int (*read64)(void *,const struct rpi5_gem_stage_session *,unsigned,uint32_t,uint32_t [16]);
    int (*barrier)(void *,const struct rpi5_gem_stage_session *);
};
int rpi5_gem_ring_batch_access_allowed(const struct rpi5_gem_stage_session *,enum rpi5_gem_stage_operation,unsigned,uint32_t);
/* Full immutable request and exact expected CPU-owned values, for the real
 * retained-provider callback to validate before its first RAM store. */
int rpi5_gem_ring_batch_values(const struct rpi5_gem_stage_session *,const struct rpi5_gem_stage_request *,unsigned,uint32_t,const uint32_t [16]);
int rpi5_gem_ring_batch(struct rpi5_gem_stage_session *,const struct rpi5_gem_stage_request *,
    const struct rpi5_gem_batch_io *,struct rpi5_gem_stage_observation *);
#ifdef __cplusplus
}
#endif
#endif
