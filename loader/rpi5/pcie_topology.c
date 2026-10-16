/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_topology.h"
#include "pcie_fdt.h"

int rpi5_pcie_topology_log(const void *fdt, size_t size,
    int (*text)(const char *), int (*hex)(uint64_t))
{
    if (!text || !hex) return -2;
    if (!text("RPI5XNU:BL33:PCIE_TOPOLOGY:BEGIN DECLARATIONS_ONLY\r\n")) return -2;
    struct rpi5_pcie_fdt binding;
    if (rpi5_fdt_pcie_rp1(fdt, size, &binding)) {
        return text("RPI5XNU:BL33:PCIE_TOPOLOGY:REJECTED NO_PCIE_ACCESS\r\n") ? -1 : -2;
    }
    if (!text("RPI5XNU:BL33:PCIE_TOPOLOGY:BRIDGE CPU_START=") ||
        !hex(binding.bridge_regs.start) || !text(" CPU_END=") ||
        !hex(binding.bridge_regs.end) || !text("\r\n") ||
        !text("RPI5XNU:BL33:PCIE_TOPOLOGY:MIP CPU_START=") ||
        !hex(binding.mip_regs.start) || !text(" MSI_PCI_TARGET=") ||
        !hex(binding.mip_target.start) || !text("\r\n") ||
        !text("RPI5XNU:BL33:PCIE_TOPOLOGY:GEM BAR_OFFSET=") ||
        !hex(binding.gem_bar_offset) || !text(" BYTES=") ||
        !hex(binding.gem_size) || !text(" RP1_IRQ=") ||
        !hex(binding.rp1_irq) || !text(" PHY_ADDRESS=") ||
        !hex(binding.phy_address) || !text("\r\n")) return -2;
    for (uint32_t i = 0; i < binding.outbound_count; i++) {
        const struct rpi5_pcie_window *window = &binding.outbound[i];
        if (!text("RPI5XNU:BL33:PCIE_TOPOLOGY:OUTBOUND SPACE=") ||
            !hex(window->space) || !text(" PCI_BASE=") || !hex(window->pci_base) ||
            !text(" CPU_BASE=") || !hex(window->cpu_base) ||
            !text(" BYTES=") || !hex(window->size) || !text(" NOT_PROGRAMMING_PROOF\r\n"))
            return -2;
    }
    return text("RPI5XNU:BL33:PCIE_TOPOLOGY:PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0\r\n") ? 0 : -2;
}
