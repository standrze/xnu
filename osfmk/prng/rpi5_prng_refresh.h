/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PRNG_REFRESH_H
#define RPI5_PRNG_REFRESH_H
#include <stddef.h>
#include <stdint.h>
enum rpi5_refresh_result {
    RPI5_REFRESH_INVALID=-3, RPI5_REFRESH_HEALTH_FAILURE=-2,
    RPI5_REFRESH_SOURCE_FAILURE=-1, RPI5_REFRESH_EMPTY=0,
    RPI5_REFRESH_RESEEDED=1, RPI5_REFRESH_BUSY=2
};
struct rpi5_refresh_ops {
    int (*try_lock)(void *);
    void (*unlock)(void *);
    int32_t (*entropy)(size_t *,void *,void *);
    int (*reseed_locked)(void *,size_t,const void *);
    void (*failure_locked)(void *,enum rpi5_refresh_result);
};
/* Callback boundary for the pinned XNU entropy_provide contract. Ops/contexts
 * must remain stable and disjoint from scratch. try_lock returns zero on
 * contention, nonzero on acquisition. reseed_locked must consume/copy its
 * input before returning, never retain its pointer or reacquire this lock.
 * It returns zero only on success; any failure invokes failure_locked and
 * returns SOURCE_FAILURE even if some generator states were already updated.
 * failure_locked must latch provider failure before returning, under the same
 * lock used by generation, without reacquiring it. A source/health failure
 * invokes it before unlock, so generation cannot slip between detection and
 * latching. INVALID callback configuration is rejected before acquiring a lock.
 * This helper does not implement generator state, locking, or kernel policy. */
enum rpi5_refresh_result rpi5_prng_refresh(const struct rpi5_refresh_ops *,
    void *lock_context,void *entropy_context,void *generator_context);
#endif
