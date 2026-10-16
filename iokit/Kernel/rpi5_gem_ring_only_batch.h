/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_RING_ONLY_BATCH_H
#define RPI5_GEM_RING_ONLY_BATCH_H
#include "rpi5_gem_ring_stage.h"
#ifdef __cplusplus
extern "C" {
#endif

#define RPI5_GEM_RING_ONLY_BATCH_BYTES 64u
#define RPI5_GEM_RING_ONLY_BATCH_WORDS 16u
#define RPI5_GEM_RING_ONLY_IO_LIMIT 81u
#define RPI5_GEM_RING_ONLY_CURRENT_LIMIT 164u

/* CPU-only descriptor initialization for the allocation retry. Packet spans
 * must all remain zero: no packet memory, queue address, ownership transfer,
 * bus mastering, DMA or IRQ is admitted by this core. The inert RX/TX
 * descriptors retain CPU ownership and carry zero packet addresses. */
struct rpi5_gem_ring_only_io {
    void *context;
    int (*current)(void *,const struct rpi5_gem_stage_session *,
        const struct rpi5_gem_stage_request *,uint64_t *);
    int (*write64)(void *,const struct rpi5_gem_stage_session *,unsigned,
        uint32_t,const uint32_t [16]);
    int (*read64)(void *,const struct rpi5_gem_stage_session *,unsigned,
        uint32_t,uint32_t [16]);
    int (*barrier)(void *,const struct rpi5_gem_stage_session *);
};
int rpi5_gem_ring_only_access_allowed(const struct rpi5_gem_stage_session *,
    enum rpi5_gem_stage_operation,unsigned,uint32_t);
int rpi5_gem_ring_only_values(const struct rpi5_gem_stage_session *,
    const struct rpi5_gem_stage_request *,unsigned,uint32_t,const uint32_t [16]);
int rpi5_gem_ring_only_batch(struct rpi5_gem_stage_session *,
    const struct rpi5_gem_stage_request *,const struct rpi5_gem_ring_only_io *,
    struct rpi5_gem_stage_observation *);
#ifdef __cplusplus
}
#endif
#endif
