/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_WATCHDOG_CONSOLE_LEASE_H
#define RPI5_PCIE_WATCHDOG_CONSOLE_LEASE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Observation-only companion to the existing terminal watchdog service.
 * This lease never writes PM_WDOG and never suppresses the service callout.
 * The provider must serialize one stable owner and retain the validated PM
 * Device mapping. Callback faults may abort or hang; they do not become I/O
 * errors. */
struct rpi5_pcie_watchdog_console_io {
    void *context;
    int (*terminal_active)(void *);
    int (*read_route)(void *, uint32_t *);
    int (*read_countdown)(void *, uint32_t *);
    int (*counter)(void *, uint64_t *);
};

enum rpi5_pcie_watchdog_console_state {
    RPI5_PCIE_CONSOLE_WDOG_EMPTY,
    RPI5_PCIE_CONSOLE_WDOG_READY,
    RPI5_PCIE_CONSOLE_WDOG_BUSY,
    RPI5_PCIE_CONSOLE_WDOG_ACTIVE,
    RPI5_PCIE_CONSOLE_WDOG_QUARANTINED,
};

struct rpi5_pcie_watchdog_console_lease {
    struct rpi5_pcie_watchdog_console_io io;
    uint64_t frequency, start, last_counter;
    uint32_t first_countdown, last_countdown, checks, callbacks;
    enum rpi5_pcie_watchdog_console_state state;
};

struct rpi5_pcie_watchdog_console_observation {
    uint64_t start, sampled_counter;
    uint32_t countdown;
};

/* Pure initialization. Storage must be zeroed and remain stable. */
int rpi5_pcie_watchdog_console_init(
    struct rpi5_pcie_watchdog_console_lease *,
    const struct rpi5_pcie_watchdog_console_io *, uint64_t frequency);

/* Claim only while the independently bounded terminal watchdog is active.
 * Requires the full-reset route and more than two seconds of actual PM
 * countdown margin. No PM write is possible through this API. */
int rpi5_pcie_watchdog_console_begin(
    struct rpi5_pcie_watchdog_console_lease *,
    struct rpi5_pcie_watchdog_console_observation *);

/* Freshly recheck terminal service, route, countdown and monotonic counter.
 * Countdown is allowed to increase because the independent terminal callout
 * owns periodic reloads. At most 1,048,576 successful checks are admitted;
 * any failure permanently quarantines the lease. */
int rpi5_pcie_watchdog_console_check(
    struct rpi5_pcie_watchdog_console_lease *);

#ifdef __cplusplus
}
#endif

#endif
