/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_TRANSFER_H
#define RPI5_SD_TRANSFER_H
#include "rpi5_sdhci_write.h"
#include "rpi5_sd_contract.h"

enum rpi5_sd_transfer_kind { RPI5_SD_TRANSFER_READ=1, RPI5_SD_TRANSFER_WRITE=2 };
enum { RPI5_SD_BUFFER_ERROR=-6, RPI5_SD_CLEANUP_ERROR=-7, RPI5_SD_CANCELLED=-8 };
/* Pure execution boundary, not linked in a running kernel. The separate
 * unlinked rpi5_sd_memory adapter retains real IOMemoryDescriptors and translates READ/WRITE to kIODirectionIn/Out,
 * supplies prepare/complete and writeBytes/readBytes callbacks, and serializes
 * this whole execution with controller/policy ownership. complete is descriptor
 * unpreparation, NOT IOStorageCompletion. The latter happens once, outside locks.
 * scratch must be kernel-owned, inaccessible to the submitter, and valid for
 * the full call: 512 bytes for reads, count*512 for writes (at most 16 KiB).
 * No allocation here; do not put a maximum-size write scratch on kernel stack.
 */
struct rpi5_sd_buffer {
    void *context;
    uint64_t bytes;
    int (*prepare)(void *, enum rpi5_sd_transfer_kind);
    int (*complete)(void *, enum rpi5_sd_transfer_kind);
    size_t (*copy_from)(void *, uint64_t, void *, size_t);
    size_t (*copy_to)(void *, uint64_t, const void *, size_t);
    int (*continuing)(void *); /* Nonzero: still online/accepting. No policy mutation. */
};
struct rpi5_sd_transfer_result {
    uint64_t actual_bytes, attempted_sectors; /* Transport calls, not observed wire commands. */
    int status, memory_status, cleanup_status;
};
/* Invalid submissions do not prepare or touch MMIO. Successful prepare is
 * paired with exactly one complete, including cancellation/error paths. Write
 * bytes are fully snapshotted before the first hardware call; policy/range is
 * checked at entry and again before every sector. Partial/ambiguous writes and
 * cleanup failures quarantine admission. Read transport failures also revoke
 * future write access by quarantining admission. Actual bytes count completed sectors,
 * NOT durable bytes. A failed copy_to can have modified the destination beyond
 * that completed prefix. This function never calls the user's I/O completion.
 */
struct rpi5_sd_transfer_result rpi5_sd_transfer(struct rpi5_sd_card *,
    struct rpi5_sd_write_policy *, uint64_t epoch, enum rpi5_sd_transfer_kind,
    uint64_t block, uint64_t count, const struct rpi5_sd_buffer *, void *scratch, size_t);
#endif
