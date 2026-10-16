/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef PE_RPI5_PCIE_WATCHDOG_CONSOLE_API_H
#define PE_RPI5_PCIE_WATCHDOG_CONSOLE_API_H

#include <stdbool.h>
#include "../../loader/rpi5/pcie_watchdog_console_lease.h"

#ifdef __cplusplus
extern "C" {
#endif

bool pe_rpi5_watchdog_claim_usb_console(const void *owner,
    struct rpi5_pcie_watchdog_console_observation *);
bool pe_rpi5_watchdog_check_usb_console(const void *owner);

#ifdef __cplusplus
}
#endif

#endif
