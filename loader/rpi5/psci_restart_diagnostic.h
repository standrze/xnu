/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PSCI_RESTART_DIAGNOSTIC_H
#define RPI5_PSCI_RESTART_DIAGNOSTIC_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Eligibility observation only. It neither consumes nor grants restart
 * authority; the actual attempt repeats all original checks and its CAS. */
int rpi5_restart_diagnostic_ready(const void *tree, size_t bytes);
void rpi5_restart_diagnostic_boot_ready(void);
#ifdef __cplusplus
}
#endif
#endif
