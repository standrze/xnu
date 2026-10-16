/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_CACHE_H
#define RPI5_SD_CACHE_H
#include "rpi5_sdhci_core.h"

enum rpi5_sd_cache_state {
    RPI5_SD_CACHE_UNKNOWN=0, RPI5_SD_CACHE_ABSENT=1,
    RPI5_SD_CACHE_DISABLED=2, RPI5_SD_CACHE_ENABLED=3
};
struct rpi5_sd_cache_observation {
    uint8_t scr[8];
    uint32_t state, specification, function, address;
    uint8_t revision, supported, enabled, flushing, cq, maintenance;
};
enum rpi5_sd_cache_probe_stage {
    RPI5_SD_CACHE_STAGE_VALIDATE=0, RPI5_SD_CACHE_STAGE_READY,
    RPI5_SD_CACHE_STAGE_APP, RPI5_SD_CACHE_STAGE_SCR_READ,
    RPI5_SD_CACHE_STAGE_SCR_DECODE, RPI5_SD_CACHE_STAGE_GENERAL_FIRST,
    RPI5_SD_CACHE_STAGE_GENERAL_SECOND, RPI5_SD_CACHE_STAGE_GENERAL_DECODE,
    RPI5_SD_CACHE_STAGE_PERFORMANCE_FIRST, RPI5_SD_CACHE_STAGE_PERFORMANCE_SECOND,
    RPI5_SD_CACHE_STAGE_PERFORMANCE_DECODE, RPI5_SD_CACHE_STAGE_COMPLETE
};
/* Diagnostic-only copy of completed read buffers. Never an admission input.
 * payload_bytes is nonzero only at a decoder stage after every corresponding
 * data/status operation succeeded. Fields are progressively observed, unlike
 * the all-or-nothing cache observation. A failed read has no valid payload.
 */
struct rpi5_sd_cache_diagnostic {
    uint32_t stage, payload_bytes, specification, function, address;
    uint8_t scr[8], payload[1024];
};
/* Pure, bounded decoding of ACTUAL read buffers, not a hardware/cache proof
 * by itself. Unknown revisions/contradictory layouts fail closed. A future
 * write profile must also bind initialized card/controller ownership/epoch.
 */
int rpi5_sd_cache_scr(const void *, size_t, unsigned *version, int *extensions);
int rpi5_sd_cache_location(const void *, size_t, unsigned *function, uint32_t *address);
int rpi5_sd_cache_performance(const void *, size_t, struct rpi5_sd_cache_observation *);
/* Read-only observation after card initialization, exclusively serialized.
 * ACMD51 reads SCR. CMD48 reads only bounded general-information/PEF pages.
 * CMD13 checks ready/state and deferred extension-command errors. No CMD49,
 * cache toggle, flush, data write, reset, DMA or retry. Output atomic on failure;
 * failed transport/protocol observation invalidates card.ready. Unknown cache
 * must not authorize writes. Even ABSENT/DISABLED is not durability acceptance.
 * Caller supplies private 1024-byte scratch outside the kernel stack, not
 * overlapping the card or output object. Controller state must come from a
 * successful initializer, not an invented ready/identity/capacity declaration.
 */
int rpi5_sd_cache_probe(struct rpi5_sd_card *, struct rpi5_sd_cache_observation *,
    void *scratch, size_t scratch_bytes);
/* Identical command/acceptance path, with optional private nonoverlapping
 * diagnostic storage. No extra MMIO, command, retry or cache-state fallback.
 */
int rpi5_sd_cache_probe_traced(struct rpi5_sd_card *, struct rpi5_sd_cache_observation *,
    void *scratch, size_t scratch_bytes, struct rpi5_sd_cache_diagnostic *);
#endif
