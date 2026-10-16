/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_MEMORY_H
#define RPI5_SD_MEMORY_H
#include <IOKit/IOMemoryDescriptor.h>
extern "C" {
#include "rpi5_sd_transfer.h"
}

/* Unlinked future write-provider adapter. The caller owns a retained descriptor
 * on entry and serializes this execution, all controller/policy operations and
 * descriptor reinitialization. Call on the single storage worker, not interrupt
 * context; do not hold the submission/completion queue lock. Allocation and
 * prepare/complete may sleep. continuing may inspect cancellation under that
 * queue lock but must not mutate card/policy or issue hardware commands.
 * This helper adds its own descriptor retain for the call, allocates bounded
 * private heap scratch (never a 16-KiB kernel-stack array), and pairs successful
 * prepares/completes. It does NOT issue IOStorageCompletion: the owning worker
 * must dequeue/free/complete once, outside locks, after this returns.
 */
struct rpi5_sd_memory_result {
    IOReturn status;
    rpi5_sd_transfer_result transfer;
};
rpi5_sd_memory_result rpi5_sd_memory_execute(rpi5_sd_card *, rpi5_sd_write_policy *,
    uint64_t epoch, rpi5_sd_transfer_kind, uint64_t block, uint64_t count,
    IOMemoryDescriptor *, int (*continuing)(void *), void *context);
#endif
