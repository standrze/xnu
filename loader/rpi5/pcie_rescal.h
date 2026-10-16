/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_RESCAL_H
#define RPI5_PCIE_RESCAL_H

#include "pcie_fdt.h"

/* Shared BCM2712 calibration block, not a per-bridge reset. The system has
 * exactly one caller-owned session for this physical resource. The provider
 * must serialize all consumers, keep controller 1's domain accessible, and
 * own the complete lifecycle through subsequent bridge/SerDes initialization.
 * claim_shared must acquire that ownership before any register callback.
 * Neither a numeric address nor this C state object establishes accessibility.
 *
 * Callbacks are bounded, non-reentrant and return zero on success. MMIO uses
 * an aligned little-endian Device mapping. order completes preceding writes.
 * now_us is monotonic (no wrap); delay_us waits AT LEAST its argument. Fault
 * containment and maximum callback latency are provider responsibilities.
 * No automatic lease release, controller shutdown, retry or rearm exists. */
struct rpi5_pcie_rescal_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*claim_shared)(void *);
    int (*read_start)(void *, uint32_t *);  /* offset 0 */
    int (*write_start)(void *, uint32_t);  /* offset 0, bit 0 only changes */
    int (*read_status)(void *, uint32_t *); /* offset 8 */
    int (*order)(void *);
    int (*now_us)(void *, uint64_t *);
    int (*delay_us)(void *, uint32_t);
};

enum rpi5_pcie_rescal_state {
    RPI5_PCIE_RESCAL_EMPTY, RPI5_PCIE_RESCAL_READY,
    RPI5_PCIE_RESCAL_BUSY, RPI5_PCIE_RESCAL_COMPLETE,
    RPI5_PCIE_RESCAL_QUARANTINED
};
enum rpi5_pcie_rescal_result {
    RPI5_PCIE_RESCAL_OK = 0, RPI5_PCIE_RESCAL_ARGUMENT = -1,
    RPI5_PCIE_RESCAL_STATE = -2, RPI5_PCIE_RESCAL_IO = -3,
    RPI5_PCIE_RESCAL_READBACK = -4, RPI5_PCIE_RESCAL_TIMEOUT = -5,
    RPI5_PCIE_RESCAL_CLOCK = -6, RPI5_PCIE_RESCAL_ALREADY_STARTED = -7
};
struct rpi5_pcie_rescal {
    struct rpi5_pcie_rescal_io io;
    enum rpi5_pcie_rescal_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_rescal_observation {
    uint32_t initial_start, asserted_start, completion_status;
    uint32_t before_clear, cleared_start, status_reads;
    uint64_t poll_elapsed_us;
};

/* Pure init. Caller zero-initializes disjoint stable objects. Exact FDT span
 * is checked, but power/clock/shared-owner/fault contracts remain prerequisites.
 * A used or quarantined session cannot be recycled with init. */
int rpi5_pcie_rescal_init(struct rpi5_pcie_rescal *,
    const struct rpi5_pcie_fdt *, const struct rpi5_pcie_rescal_io *);

/* One initial calibration: claim -> observe idle START -> set bit 0 -> verify
 * -> poll STATUS bit 0 at up to 100-us intervals for at most 1000 us -> clear
 * START preserving other bits -> order and verify. Maximum 11 status reads,
 * ten delays; actual elapsed time is independently checked after reads/delays.
 * An already-set START is not ours to steal and is rejected without a write.
 * Completion uses the reference provider's level predicate, NOT a proof of a
 * new completion edge, calibrated accuracy, trained PCIe link or usable NIC.
 * Failure immediately quarantines, leaves out unchanged and performs no
 * cleanup write or release. Even a failed write/claim may have taken effect.
 * Keep shared ownership until a higher-level recovery decision; do not power
 * off controller 1 or retry under another per-controller session.
 * This primitive has no MMIO caller or boot integration yet. */
int rpi5_pcie_rescal_calibrate(struct rpi5_pcie_rescal *,
    struct rpi5_pcie_rescal_observation *out);

#endif
