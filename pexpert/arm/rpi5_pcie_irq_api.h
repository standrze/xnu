/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef PE_RPI5_PCIE_IRQ_API_H
#define PE_RPI5_PCIE_IRQ_API_H
#include <stdbool.h>
#include "../../loader/rpi5/pcie_irq_mask.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Distinct opt-in DEVELOPMENT kernel only. Caller supplies an actual decoded
 * retained firmware-FDT binding, exclusive firmware/controller lifecycle and
 * stable owner identity. The SAME identity must already own the one-shot PM
 * lease. Claim requires thread context with local DAIF.I/F masked; the caller
 * must not restore interrupts after failed claim until recovery. Successful
 * claim retains/binds current_thread(), suppresses only the exact PCIe2 NS GIC bits,
 * and never releases/restores them. Check can run with local IRQs enabled.
 * No secure-bank, MIP/controller-source, endpoint/DMA or reset-return proof is
 * inferred from MASKED or a zero inaccessible bank read. No activation caller
 * is added by these APIs. Output is unchanged on all returned failures. */
bool pe_rpi5_pcie_irq_claim(const void *, const struct rpi5_pcie_fdt *, struct rpi5_pcie_irq_observation *);
bool pe_rpi5_pcie_irq_check(const void *, struct rpi5_pcie_irq_observation *);
#ifdef __cplusplus
}
#endif
#endif
