/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef PE_RPI5_PCIE_WATCHDOG_API_H
#define PE_RPI5_PCIE_WATCHDOG_API_H
#include <stdbool.h>
#include "../../loader/rpi5/pcie_watchdog_lease.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Only a distinct DEVELOPMENT kernel with the opt-in watchdog patch provides
 * these symbols. Stable non-null owner identity, serialized thread context.
 * Claim is destructive to ordinary watchdog SERVICING until the next reset,
 * including on failure; it does not change reset routing or boot selection.
 * Calling success is NOT a safe-reset-destination or physical timing receipt.
 * No production driver may use this short diagnostic lease indefinitely. */
bool pe_rpi5_watchdog_claim_pcie(const void *owner, struct rpi5_pcie_watchdog_observation *);
bool pe_rpi5_watchdog_check_pcie(const void *owner);
#ifdef __cplusplus
}
#endif
#endif
