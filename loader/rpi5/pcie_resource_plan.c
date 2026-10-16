/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_resource_plan.h"

#define PHYS_LIMIT (UINT64_C(1) << 40)
#define PAGE_BYTES UINT64_C(0x4000)
#define PCI_MEM32 UINT32_C(0x02000000)
#define PCI_PREFETCH64 UINT32_C(0x43000000)

static int span(uint64_t base, uint64_t size, uint64_t limit)
{
    return size && base < limit && size <= limit - base;
}

static int power_of_two(uint64_t value)
{
    return value && (value & (value - 1)) == 0;
}

/* The two FDT windows are declarations, not evidence that the controller has
 * programmed them. Search only PCI memory-space windows and reject ambiguity. */
static int translate_mem32(const struct rpi5_pcie_fdt *binding,
    uint64_t pci_base, uint64_t size, uint64_t *cpu_base)
{
    uint32_t matches = 0;
    uint64_t translated = 0;
    if (!span(pci_base, size, PHYS_LIMIT) ||
        !binding->outbound_count || binding->outbound_count > 2) return -1;
    for (uint32_t i = 0; i < binding->outbound_count; i++) {
        const struct rpi5_pcie_window *w = &binding->outbound[i];
        if ((w->space != PCI_MEM32 && w->space != PCI_PREFETCH64) ||
            !span(w->pci_base, w->size, PHYS_LIMIT) ||
            !span(w->cpu_base, w->size, PHYS_LIMIT)) return -1;
        if (w->space != PCI_MEM32 || pci_base < w->pci_base) continue;
        uint64_t offset = pci_base - w->pci_base;
        if (offset >= w->size || size > w->size - offset) continue;
        translated = w->cpu_base + offset;
        if (!span(translated, size, PHYS_LIMIT)) return -1;
        matches++;
    }
    if (matches != 1) return -1;
    *cpu_base = translated;
    return 0;
}

static int region(uint64_t bar_cpu, uint64_t bar_size,
    uint64_t aperture_size, uint64_t offset, uint64_t size,
    struct rpi5_range *exact, struct rpi5_range *pages)
{
    if (!span(offset, size, aperture_size) ||
        !span(offset, size, bar_size)) return -1;
    struct rpi5_range e = {bar_cpu + offset, bar_cpu + offset + size};
    struct rpi5_range p = {
        e.start & ~(PAGE_BYTES - 1),
        ((e.end - 1) | (PAGE_BYTES - 1)) + 1
    };
    if (p.start < bar_cpu || p.end > bar_cpu + bar_size ||
        p.end > PHYS_LIMIT) return -1;
    *exact = e;
    *pages = p;
    return 0;
}

int rpi5_pcie_resource_plan(const struct rpi5_pcie_fdt *binding,
    const struct rpi5_rp1_bar_observation *bar,
    struct rpi5_pcie_resource_plan *out)
{
    if (!binding || !bar || !out ||
        bar->vendor_id != UINT16_C(0x1de4) || bar->device_id != UINT16_C(0x0001) ||
        bar->bar_index != 1 || bar->assigned != 1 ||
        bar->memory_decode_enabled != 1 || bar->space != PCI_MEM32 ||
        !power_of_two(bar->size) || bar->pci_base & (bar->size - 1) ||
        !span(bar->pci_base, bar->size, PHYS_LIMIT) ||
        binding->rp1_pci_base != 0 || !binding->rp1_aperture_size) return -1;

    /* The FDT child's static PCI base describes a reachable declaration,
     * not an observed BAR assignment. The child aperture can extend beyond
     * BAR1 into other RP1 BARs; only requested regions must fit in BAR1. */
    uint64_t declared_cpu, bar_cpu;
    if (translate_mem32(binding, binding->rp1_pci_base,
            binding->rp1_aperture_size, &declared_cpu) ||
        translate_mem32(binding, bar->pci_base, bar->size, &bar_cpu) ||
        (bar_cpu & (PAGE_BYTES - 1))) return -1;
    (void)declared_cpu;

    struct rpi5_pcie_resource_plan plan = {0};
    plan.bar_cpu = (struct rpi5_range){bar_cpu, bar_cpu + bar->size};
    if (region(bar_cpu, bar->size, binding->rp1_aperture_size,
            binding->gem_bar_offset, binding->gem_size,
            &plan.gem_cpu, &plan.gem_pages) ||
        region(bar_cpu, bar->size, binding->rp1_aperture_size,
            binding->clock_bar_offset, binding->clock_size,
            &plan.clock_cpu, &plan.clock_pages)) return -1;
    *out = plan;
    return 0;
}
