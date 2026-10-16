/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_WATCHDOG_LEASE_H
#define RPI5_PCIE_WATCHDOG_LEASE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* One-shot diagnostic lease, never a steady-state network watchdog. Provider
 * must exclusively stop ALL other watchdog writers before begin and retain
 * an accessible Device mapping of the independently validated BCM2712 PM.
 * Read/write callbacks are real ordered numeric LE accesses; faults may hang
 * or abort, not return IO errors. Autonomous PM reset/routing and the next boot
 * destination still require hardware evidence. No reset-route/RSTS writes. */
struct rpi5_pcie_watchdog_io {
    void *context;
    int (*read_route)(void *, uint32_t *);
    int (*read_countdown)(void *, uint32_t *);
    int (*write_countdown)(void *, uint32_t);
    int (*order)(void *);
    int (*counter)(void *, uint64_t *);
};
enum rpi5_pcie_watchdog_state {
    RPI5_PCIE_WDOG_EMPTY, RPI5_PCIE_WDOG_READY, RPI5_PCIE_WDOG_BUSY,
    RPI5_PCIE_WDOG_ARMED, RPI5_PCIE_WDOG_QUARANTINED
};
struct rpi5_pcie_watchdog_lease {
    struct rpi5_pcie_watchdog_io io;
    uint64_t frequency, start, deadline, last_counter;
    uint32_t first_countdown, last_countdown, checks, callbacks;
    enum rpi5_pcie_watchdog_state state;
};
struct rpi5_pcie_watchdog_observation {
    uint64_t start, deadline, sampled_counter;
    uint32_t prior_countdown, armed_countdown;
};
/* Pure init, zeroed/disjoint stable storage, nonzero counter frequency. */
int rpi5_pcie_watchdog_init(struct rpi5_pcie_watchdog_lease *,
    const struct rpi5_pcie_watchdog_io *, uint64_t frequency);
/* Already-running full-reset countdown required. Exactly one 15-second WDOG
 * write, eight callbacks. Arming must return within one counter second;
 * diagnostic access ends at start+12 seconds. Output unchanged on failure.
 * BUSY is set before callbacks, so reentry/rearm/retry is rejected. */
int rpi5_pcie_watchdog_begin(struct rpi5_pcie_watchdog_lease *,
    struct rpi5_pcie_watchdog_observation *);
/* Four callbacks, NEVER a reload. Require full-reset route, >2-second actual
 * hardware margin, nonincreasing countdown, nonregressing counter and unexpired
 * deadline. After one counter millisecond the hardware count must have fallen.
 * At most 65,536 checks even if counter/countdown stall. No close/cancel/release;
 * success and failure both leave ordinary servicing prohibited until reset.
 * Finite checks do not bound a hung callback; autonomous hardware is separate. */
int rpi5_pcie_watchdog_check(struct rpi5_pcie_watchdog_lease *);
#ifdef __cplusplus
}
#endif
#endif
