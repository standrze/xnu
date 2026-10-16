/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SDHCI_WRITE_H
#define RPI5_SDHCI_WRITE_H
#include "rpi5_sdhci_core.h"
#include "rpi5_sd_write_policy.h"

/* Offline candidate, NOT in either read-only image or the provider build.
 * Caller owns the controller exclusively and holds the policy/request epoch
 * stable for the entire synchronous operation. Copy from a retained/prepared
 * IOMemoryDescriptor before calling; this routine snapshots exactly 512 bytes
 * into its own buffer before any controller write. No DMA, IRQ, erase,
 * multi-block write, retry, reset or reinitialization is implemented.
 * Success means transfer completion + DATA_INHIBIT clear + CMD13 READY/TRAN.
 * It is NOT a cache-flush primitive or power-loss durability guarantee.
 * Any hardware-phase failure clears card.ready and permanently quarantines
 * the policy; the sector may have changed and must not be silently retried.
 */
int rpi5_sd_write_sector(struct rpi5_sd_card *, struct rpi5_sd_write_policy *,
    uint64_t epoch, uint64_t lba, const void *, size_t bytes);
/* Status wait only. Does not issue data, a cache flush, erase or card reset. */
int rpi5_sd_write_wait_ready(struct rpi5_sd_card *, struct rpi5_sd_write_policy *, uint64_t epoch);
#endif
