/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PSCI_RESTART_CANDIDATE_H
#define RPI5_PSCI_RESTART_CANDIDATE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Candidate only. Zero-initialized, kernel-owned, retained until reset. Once an
 * admitted attempt starts, neither failure nor a returned SMC permits retry.
 * Caller supplies the retained, immutable SAME-BOOT firmware tree, not a user
 * pointer. This does not authenticate firmware or authorize bypassing shutdown.
 */
struct rpi5_restart_once { uint32_t entered; };
enum rpi5_restart_result {
    RPI5_RESTART_REFUSED = -1,
    RPI5_RESTART_BUSY = -2,
    RPI5_RESTART_VERSION = -3,
    RPI5_RESTART_UNSUPPORTED = -4,
    RPI5_RESTART_RETURNED = -5
};
/* There is deliberately NO successful return. A successful SYSTEM_RESET never
 * returns to its caller. No SYSTEM_OFF, CPU_OFF, reset2, MMIO or fallback reset.
 */
int rpi5_restart_attempt(struct rpi5_restart_once *, const void *, size_t);
uint64_t rpi5_restart_current_el(void);
uint64_t rpi5_restart_psci_version(void);
uint64_t rpi5_restart_psci_feature(void);
uint64_t rpi5_restart_psci_reset(void);
#ifdef __cplusplus
}
#endif
#endif
