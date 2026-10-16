/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_RESOURCE_PLAN_H
#define RPI5_PCIE_RESOURCE_PLAN_H

#include <stdint.h>
#include "pcie_fdt.h"

/* Separately observed PCI configuration/resource facts for RP1 BAR1. The
 * address is in PCI bus space, not a host CPU physical address. In particular,
 * Linux pci_resource_start(pdev, 1) is already a translated host resource and
 * must not be supplied as pci_base. Base zero may be a valid assignment: the
 * assigned flag must come from independent enumeration evidence. */
struct rpi5_rp1_bar_observation {
    uint16_t vendor_id, device_id;
    uint32_t bar_index, assigned, memory_decode_enabled, space;
    uint64_t pci_base, size;
};

/* Half-open CPU physical spans. *_cpu are the exact decoded register extents;
 * *_pages are the enclosing 16 KiB page extents proposed for Device mapping.
 * bar_cpu is the entire live BAR1 aperture, not just the FDT RP1 child range. */
struct rpi5_pcie_resource_plan {
    struct rpi5_range bar_cpu;
    struct rpi5_range gem_cpu, gem_pages;
    struct rpi5_range clock_cpu, clock_pages;
};

/* Pure, freestanding reconciliation of a successfully decoded FDT binding
 * with independently observed RP1 BAR1 facts. Validates unique full-span PCI
 * MEM32 outbound containment, BAR alignment/size, 40-bit CPU bounds and page
 * containment. The FDT's rp1_pci_base is a static PCI child declaration; it
 * must be the zero-based static aperture in this Pi 5 profile and is never
 * used as the live BAR address. The FDT aperture may cover other RP1 BARs;
 * only the requested GEM and clock regions must fit in BAR1. Output is
 * unchanged on failure. Input and output objects must be disjoint and stable.
 *
 * Caller must independently verify PCI identity, BAR1 assignment/type/size,
 * the PCI command memory-decode bit and that the bridge outbound window is
 * actually programmed. This routine performs no MMIO, PCI writes, DMA or
 * mapping, and its result alone is not permission to access a device. */
int rpi5_pcie_resource_plan(const struct rpi5_pcie_fdt *binding,
    const struct rpi5_rp1_bar_observation *bar,
    struct rpi5_pcie_resource_plan *out);

#endif
