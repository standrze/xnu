/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef PE_RPI5_PCIE_FW_API_H
#define PE_RPI5_PCIE_FW_API_H
#include <stdbool.h>
#include "../../loader/rpi5/pcie_fw_client.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Same real owner/thread must already own PM and selective NS IRQ leases.
 * Claim requires masked local I/F; failures are terminal until autonomous
 * reset. One retained thread, no unmap/release/retry. Check may run IRQ-enabled.
 * This verifies the private EL3 facts, NOT whole power/source/endpoint/DMA
 * admission, firmware isolation, controller activation or physical recovery. */
bool pe_rpi5_pcie_fw_claim(const void *,struct rpi5_fw_observation *);
bool pe_rpi5_pcie_fw_check(const void *,struct rpi5_fw_observation *);
#ifdef __cplusplus
}
#endif
#endif
