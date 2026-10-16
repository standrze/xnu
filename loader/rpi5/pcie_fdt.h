/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_FDT_H
#define RPI5_PCIE_FDT_H

#include <stddef.h>
#include <stdint.h>
#include "ranges.h"

/* A decoded PCI ranges/dma-ranges row. Space is the PCI phys.hi cell, without
 * bus/device/function/register bits. These are declarations, not programmed
 * windows or permission to use an address for DMA. */
struct rpi5_pcie_window {
    uint32_t space;
    uint64_t pci_base, cpu_base, size;
};

/* An RP1 dma-ranges row. The RP1 address is distinct from a CPU physical
 * address; in particular the GEM register address is not directly mappable. */
struct rpi5_rp1_dma_window {
    uint32_t space;
    uint64_t rp1_base, pci_base, size;
};

struct rpi5_pcie_fdt {
    /* Only bridge_regs and mip_regs are translated CPU physical MMIO. The
     * mip_target is an untranslated PCI/MSI bus address, outside /axi/ranges. */
    struct rpi5_range bridge_regs, mip_regs, mip_target;
    struct rpi5_range rescal_regs, bridge_reset_regs;
    struct rpi5_pcie_window outbound[2], dma[3];
    struct rpi5_rp1_dma_window rp1_dma[3];
    uint32_t outbound_count, dma_count, rp1_dma_count;

    uint32_t gic_phandle, mip_phandle, rp1_phandle, clock_phandle;
    uint32_t phy_phandle, phy_address;
    uint32_t bridge_intid[2], intx_intid[4];
    uint32_t mip_intid_base, mip_intid_count;
    uint32_t bridge_reset_id;
    uint32_t rp1_irq, rp1_irq_flags, gem_clock_id[4];

    uint64_t rp1_local_base, rp1_pci_base, rp1_aperture_size;
    uint64_t clock_bar_offset, clock_size;
    uint64_t gem_bar_offset, gem_size;
};

/* Decode only the enabled Pi 5 PCIe2 -> MIP0 -> RP1 -> GEM FDT profile. All
 * output is derived from the caller's stable readable FDT and is committed
 * only after every binding, size, link, and address check succeeds. The BAR is
 * unassigned here: gem_bar_offset is relative to RP1's PCI memory aperture,
 * never a CPU physical address. No MMIO, reset, interrupt or DMA is performed.
 * Returns 0 on success and -1 on unsupported or malformed input. */
int rpi5_fdt_pcie_rp1(const void *fdt, size_t size, struct rpi5_pcie_fdt *out);

#endif
