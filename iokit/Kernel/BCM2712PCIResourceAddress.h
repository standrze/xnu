/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCI_RESOURCE_ADDRESS_H
#define BCM2712_PCI_RESOURCE_ADDRESS_H
#include <IOKit/pci/IOPCIDevice.h>
#include "../../loader/rpi5/pcie_fdt.h"

/* Pure conversion of ORIGINAL IOPCIFamily assigned-addresses, not raw FDT
 * big-endian cells. In particular, IOPCIPhysicalAddress has architecture-
 * dependent field ordering. Do not parse it as an assumed five-word layout.
 * This is not assignment evidence, live BAR readback or mapping permission. */
struct bcm2712_pci_resource_address {
    uint32_t tag;
    uint64_t pci_base, size, cpu_base;
};

static inline bool bcm2712_pci_resource_span(uint64_t base, uint64_t size,
    uint64_t limit)
{
    return size && base < limit && size <= limit - base;
}

static inline bool bcm2712_pci_resource_overlap(uint64_t a, uint64_t size_a,
    uint64_t b, uint64_t size_b)
{
    return a < b + size_b && b < a + size_a;
}

static inline bool bcm2712_pci_resource_windows_valid(
    const struct rpi5_pcie_window *windows, uint32_t count)
{
    if (!windows || count != 2) return false;
    for (unsigned i = 0; i < 2; i++) {
        const auto &w = windows[i];
        if (w.space != (i ? UINT32_C(0x43000000) : UINT32_C(0x02000000)) ||
            !bcm2712_pci_resource_span(w.pci_base, w.size, UINT64_C(1) << (i ? 40 : 32)) ||
            !bcm2712_pci_resource_span(w.cpu_base, w.size, UINT64_C(1) << 40)) return false;
    }
    return !bcm2712_pci_resource_overlap(windows[0].pci_base, windows[0].size,
               windows[1].pci_base, windows[1].size) &&
        !bcm2712_pci_resource_overlap(windows[0].cpu_base, windows[0].size,
               windows[1].cpu_base, windows[1].size);
}

/* At most six BAR records, including the upper slot consumed by a MEM64 BAR.
 * ROM, PCI I/O, aliases, missing reloc/assignment tags and unknown flag bits
 * are unsupported. No descriptor/heap/kernel call occurs. Inputs/outputs must
 * be disjoint and stable. On failure both output array and count are unchanged.
 * Base zero is valid in an independently assigned record. Decode rounding is
 * never allocatable: containment uses the declared outbound size only. */
static inline bool bcm2712_pci_resource_addresses(
    const struct rpi5_pcie_window *windows, uint32_t window_count,
    const void *bytes, size_t length, IOPCIAddressSpace device,
    struct bcm2712_pci_resource_address out[6], uint32_t *out_count)
{
    if (!out || !out_count || !bcm2712_pci_resource_windows_valid(windows, window_count) ||
        length > 6 * sizeof(IOPCIPhysicalAddress) || length % sizeof(IOPCIPhysicalAddress) ||
        (length && !bytes) || (device.bits & ~UINT32_C(0x00ffff00)) ||
        device.s.busNum > 1 || device.s.deviceNum || device.s.functionNum) return false;
    struct bcm2712_pci_resource_address result[6] = {};
    uint32_t count = (uint32_t)(length / sizeof(IOPCIPhysicalAddress)), slots = 0;
    for (uint32_t i = 0; i < count; i++) {
        IOPCIPhysicalAddress row;
        auto dst = reinterpret_cast<unsigned char *>(&row);
        const auto src = static_cast<const unsigned char *>(bytes) + i * sizeof(row);
        for (size_t j = 0; j < sizeof(row); j++) dst[j] = src[j];
        const auto flags = row.physHi;
        if ((flags.bits & ~UINT32_C(0xc3ffffff)) || !flags.s.reloc ||
            (flags.bits & UINT32_C(0x00ffff00)) != device.bits ||
            flags.s.registerNum < kIOPCIConfigBaseAddress0 ||
            flags.s.registerNum > kIOPCIConfigBaseAddress5 ||
            ((flags.s.registerNum - kIOPCIConfigBaseAddress0) & 3)) return false;
        unsigned window;
        if (flags.s.space == kIOPCI32BitMemorySpace && !flags.s.prefetch) window = 0;
        else if (flags.s.space == kIOPCI64BitMemorySpace && flags.s.prefetch) window = 1;
        else return false;
        unsigned slot = (flags.s.registerNum - kIOPCIConfigBaseAddress0) / 4;
        if (window && slot == 5) return false;
        uint32_t used = (window ? 3u : 1u) << slot;
        if (slots & used) return false;
        slots |= used;
        uint64_t base = ((uint64_t)row.physMid << 32) | row.physLo;
        uint64_t size = ((uint64_t)row.lengthHi << 32) | row.lengthLo;
        const auto &w = windows[window];
        if (size < 16 || (size & (size - 1)) || (base & (size - 1)) ||
            !bcm2712_pci_resource_span(base, size, UINT64_C(1) << (window ? 40 : 32)) ||
            base < w.pci_base || base - w.pci_base >= w.size ||
            size > w.size - (base - w.pci_base)) return false;
        uint64_t cpu = w.cpu_base + (base - w.pci_base);
        if (!bcm2712_pci_resource_span(cpu, size, UINT64_C(1) << 40)) return false;
        for (uint32_t j = 0; j < i; j++) {
            if (bcm2712_pci_resource_overlap(base, size, result[j].pci_base, result[j].size) ||
                bcm2712_pci_resource_overlap(cpu, size, result[j].cpu_base, result[j].size))
                return false;
        }
        result[i].tag = flags.bits;
        result[i].pci_base = base;
        result[i].size = size;
        result[i].cpu_base = cpu;
    }
    for (uint32_t i = 0; i < count; i++) out[i] = result[i];
    *out_count = count;
    return true;
}
#endif
