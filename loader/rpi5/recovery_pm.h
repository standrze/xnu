/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RECOVERY_PM_H
#define RPI5_RECOVERY_PM_H
#include "pcie_watchdog_lease.h"
enum { RPI5_RECOVERY_ARMED = 1, RPI5_RECOVERY_CHECKED = 2 };
struct rpi5_recovery_observation {
    struct rpi5_pcie_watchdog_observation watchdog;
    uint64_t frequency, waited_ticks;
    uint32_t route, final_countdown, checks;
};
/* Fixed-address ordered assembly leaves, not a general MMIO API. */
uint32_t rpi5_recovery_route(void);
uint32_t rpi5_recovery_countdown(void);
void rpi5_recovery_write_countdown(uint32_t);
void rpi5_recovery_order(void);
uint64_t rpi5_recovery_counter(void);
#endif
