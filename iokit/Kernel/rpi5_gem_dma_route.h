/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_DMA_ROUTE_H
#define RPI5_GEM_DMA_ROUTE_H
#ifdef __cplusplus
extern "C" {
#endif
#include "../../loader/rpi5/fdt.h"
#include "../../loader/rpi5/pcie_windows.h"
struct rpi5_gem_dma_route {
    uint64_t physical, pci, rp1, bytes;
};
/* Pure complete-span composition, NOT allocation, live readback or DMA authority.
 * Accept only the preferred RP1 64-bit RAM route, never the low alias, MIP or
 * device route. Compare every programmed encoding with the newly decoded FDT.
 * The caller separately owns wired normal RAM and fresh live window checks.
 * Unresolved dynamic reservation windows are conservatively excluded in full;
 * this does not pretend that firmware allocated those windows. No output on
 * failure. Stable, disjoint input/output objects are caller obligations. */
int rpi5_gem_dma_route(const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_window_plan *, const struct rpi5_fdt_memory *,
    const struct rpi5_reservation_plan *, const struct rpi5_range *initrd,
    uint64_t physical, uint64_t bytes, struct rpi5_gem_dma_route *);
#ifdef __cplusplus
}
#endif
#endif
