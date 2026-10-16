/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_BARS_PLAN_H
#define RPI5_RP1_BARS_PLAN_H
#include "rp1_bars_probe.h"
#include "pcie_fdt.h"
struct rpi5_rp1_bars_plan {
    uint32_t pci_base[6], present;
    struct rpi5_range cpu[6];
    struct rpi5_range gem_pages, clock_pages;
};
/* Pure candidate allocation from a completed same-boot all-slot size/restore
 * session and decoded FDT. BAR1 stays at PCI zero so RP1 child offsets retain
 * their binding meaning. Remaining MEM32 apertures are placed largest-first
 * with natural alignment and no pairwise overlap in one declared host window.
 * All six slots are reconciled, including absent zero-mask slots. Rejects
 * unsupported shapes, 32/40-bit overflow, truncated/ambiguous windows and GEM
 * or clock pages outside BAR1. Output unchanged on failure.
 *
 * NOT an assignment receipt: no BAR/COMMAND/MMIO writes, Device mapping or
 * DMA authority. A later programmer must retain the live ownership lease,
 * verify actual outbound programming and every programmed endpoint BAR before
 * COMMAND.MEM. No capability of the endpoint to DMA is enabled by this plan. */
int rpi5_rp1_bars_assignment_plan(const struct rpi5_pcie_fdt *,
    const struct rpi5_rp1_bars_probe *, const struct rpi5_rp1_bars_size *,
    struct rpi5_rp1_bars_plan *);
#endif
