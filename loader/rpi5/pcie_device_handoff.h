/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_DEVICE_HANDOFF_H
#define RPI5_PCIE_DEVICE_HANDOFF_H
#include "memory_type.h"

/* Pure declaration expansion. Strictly decode the complete raw Pi5 PCIe/RP1
 * profile, then add ONLY the three rounded PHY transport resources (five 16K
 * pages) to a valid memory-type contract. Preserve existing records verbatim.
 * Reject duplicate/overlapping additions, RAM overlap and capacity exhaustion.
 * Stable readable/disjoint input, FDT and output; failure preserves output.
 * NO MMIO, power/clock/ownership permission, IRQ, DMA or endpoint BAR mapping.
 * Device typing is necessary for pmap, never sufficient for physical access. */
int rpi5_pcie_device_handoff(const void *fdt, size_t fdt_bytes,
    const struct rpi5_memory_types *input, struct rpi5_memory_types *out);
#endif
