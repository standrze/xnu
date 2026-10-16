/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_DMA_ROUTE_H
#define RPI5_RP1_DMA_ROUTE_H

#ifdef __cplusplus
extern "C" {
#endif

#include "../../loader/rpi5/fdt.h"
#include "../../loader/rpi5/pcie_windows.h"

struct rpi5_rp1_dma_route {
    uint64_t physical, pci, rp1, bytes;
};

/* Pure complete-span composition, not allocation or DMA authority.  Only the
 * preferred 64-bit RP1 RAM route is accepted.  The caller separately owns the
 * wired memory and proves the live decoder state immediately before use. */
int rpi5_rp1_dma_route(const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_window_plan *, const struct rpi5_fdt_memory *,
    const struct rpi5_reservation_plan *, const struct rpi5_range *initrd,
    uint64_t physical, uint64_t bytes, struct rpi5_rp1_dma_route *);

#ifdef __cplusplus
}
#endif

#endif
