/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_CONFIG_H
#define RPI5_PCIE_CONFIG_H
#include "pcie_link.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_pcie_config_request {
    uint32_t bus, device, function, offset, width, write, value;
};

/* Same stable owner/context and exact Device mapping as the completed link.
 * acquire/release serialize ALL accesses to the controller config selector,
 * including other diagnostics, and protect session state. acquire may fail
 * without ownership; release is mandatory/void and must not do MMIO or fail.
 * All callbacks must terminate independently; this is NOT abort-safe MMIO.
 * read/write are real numeric little-endian accesses of width 1, 2 or 4.
 * In particular, writes must never emulate subwords with 32-bit RMW.
 * check_lifecycle must retain power/clocks, accessibility, recovery containment
 * and exclusive controller lifecycle, even while the lock is held. It must
 * not assert PERST/link-down as earlier bring-up callbacks did.
 * authorize_write must independently admit EVERY config write, including BAR
 * sizing/assignment, bridge bus ranges, resets, interrupts/MSI and bus master
 * bits. A successful callback is an owner obligation, not hardware evidence.
 * Nothing in software COMPLETE states or this interface grants DMA permission.
 * Callbacks must not reenter; acquire must refuse same-thread recursion. */
struct rpi5_pcie_config_io {
    void *context;
    int (*acquire)(void *);
    void (*release)(void *);
    int (*check_lifecycle)(void *);
    int (*authorize_write)(void *, const struct rpi5_pcie_config_request *);
    int (*read)(void *, uint32_t offset, uint32_t width, uint32_t *);
    int (*write)(void *, uint32_t offset, uint32_t width, uint32_t);
    int (*order)(void *);
};
enum rpi5_pcie_config_state {
    RPI5_PCIE_CONFIG_EMPTY, RPI5_PCIE_CONFIG_READY,
    RPI5_PCIE_CONFIG_BUSY, RPI5_PCIE_CONFIG_QUARANTINED
};
enum rpi5_pcie_config_result {
    RPI5_PCIE_CONFIG_OK = 0, RPI5_PCIE_CONFIG_ARGUMENT = -1,
    RPI5_PCIE_CONFIG_ABSENT = -2, RPI5_PCIE_CONFIG_STATE = -3,
    RPI5_PCIE_CONFIG_DEPENDENCY = -4, RPI5_PCIE_CONFIG_LOCK = -5,
    RPI5_PCIE_CONFIG_IO = -6, RPI5_PCIE_CONFIG_LINK = -7,
    RPI5_PCIE_CONFIG_SELECTOR = -8, RPI5_PCIE_CONFIG_DENIED = -9,
    RPI5_PCIE_CONFIG_VALUE = -10
};
struct rpi5_pcie_config {
    struct rpi5_pcie_config_io io;
    struct rpi5_pcie_link *link;
    enum rpi5_pcie_config_state state; /* Inspect only under io lock after publication. */
    uint32_t initialized; /* Immutable once published. */
};

/* Pure init; zeroed, disjoint/stable objects, before publication/concurrency.
 * Requires COMPLETE link/RC/windows/UBUS for the same owner and PCIe2 mapping.
 * No callback, hardware access, reset, link train or ownership acquisition. */
int rpi5_pcie_config_init(struct rpi5_pcie_config *, struct rpi5_pcie_link *,
    const struct rpi5_pcie_config_io *);

/* Root 00:00.0 or fixed RP1 01:00.0; 4-KiB config spaces only. Other valid
 * BDFs return ABSENT without I/O. Unaligned/out-of-range/malformed inputs reject
 * without I/O. Non-aliasing read output unchanged unless the entire transaction
 * succeeds; all-ones CONFIG data is legitimate (absent/unimplemented register).
 * Under lock: lifecycle, ordering, RC/link checks, selector write/order/readback
 * for RP1, true-width data access, final checks. <=15 callbacks, no retry/poll.
 * Root config can be read with link down, but requires RC role and not L23.
 * Unexpected selector/link/readback/lifecycle/authorization/IO failure latches
 * quarantine; only release runs afterward, with no cleanup/rollback. Writes
 * may already have taken effect. Invalid request/ABSENT/lock failure does not
 * mutate the session; a failed acquire never permits unlocked state mutation.
 * Sampling link status cannot prevent a racing CPU abort: actual containment
 * and lifecycle safety still belong to the provider. Not wired into boot code. */
int rpi5_pcie_config_transfer(struct rpi5_pcie_config *,
    const struct rpi5_pcie_config_request *, uint32_t *read_value);
int rpi5_pcie_config_ready(struct rpi5_pcie_config *); /* Locked state/dependency query, no MMIO. */

#ifdef __cplusplus
}
#endif
#endif
