/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_RAM_WINDOW_H
#define RPI5_GEM_RAM_WINDOW_H
#ifdef __cplusplus
extern "C" {
#endif
#include "pcie_windows.h"

/* Pure, narrowly selected Pi5 PCIe2/RP1 encoding. Only the preferred RAM
 * viewport (hardware inbound BAR2) has a nonzero size. Device BAR1 and MIP
 * BAR3 remain disabled; unused hardware BAR4..10 are an independent runtime
 * provider obligation. All original outbound fields are retained exactly.
 *
 * This is NOT a write, live readback, installed-RAM, allocation, cache, bus
 * mastering, queue ownership, or DMA-completion authority. The existing
 * programmer must still prove held PERST/link-down for every window write;
 * the released owner must independently read back every programmed field.
 * The 64GiB viewport size does not describe the installed RAM size.
 * Inputs/output must remain stable and disjoint. Output is atomic on error.
 */
int rpi5_gem_ram_window_plan(const struct rpi5_pcie_fdt *,
    struct rpi5_pcie_window_plan *);
int rpi5_gem_ram_window_match(const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_window_plan *);
#ifdef __cplusplus
}
#endif
#endif
