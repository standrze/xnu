/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_FW_VERIFIER_H
#define RPI5_PCIE_FW_VERIFIER_H
#include <stdint.h>
/* Private development SiP64 ABI, not an allocated public/vendor standard. */
#define RPI5_FW_PCIE_QUERY UINT32_C(0xc2007f10)
#define RPI5_FW_PCIE_CLAIM UINT32_C(0xc2007f11)
#define RPI5_FW_PCIE_CHECK UINT32_C(0xc2007f12)
#define RPI5_FW_PCIE_ABI UINT32_C(1)
enum { RPI5_FW_GROUP1=1, RPI5_FW_MASKED=2, RPI5_FW_C1_RELEASED=4,
    RPI5_FW_RESCAL_READ=8, RPI5_FW_WATCHDOG=16 };
enum { RPI5_FW_OK=0, RPI5_FW_ARGUMENT=-1, RPI5_FW_STATE=-2,
    RPI5_FW_HARDWARE=-3, RPI5_FW_CLOCK=-4 };
struct rpi5_fw_observation { uint64_t counter; uint32_t sequence, facts; };
/* Query: owner zero, before claim, GIC group/mask/active observations only.
 * Claim/check: stable nonzero opaque trusted-NS-kernel owner token; selected
 * SPIs must already be disabled by the real NS lease and PM already armed.
 * No arbitrary address/value arguments, hardware writes, grant to DMA, reset,
 * enable, clear-pending/active, clock control or release/retry API. */
int rpi5_fw_verifier_call(uint32_t fid, uint64_t owner, struct rpi5_fw_observation *);
/* Ordered production leaves; the private fixed-address list is in the core.
 * Core is also executed with explicit host doubles.
 * A bus abort/hang does not return an invented I/O error. */
uint32_t rpi5_fw_load32(uint64_t address);
uint64_t rpi5_fw_counter(void);
uint64_t rpi5_fw_frequency(void);
#endif
