/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCI_ASSIGNED_RANGE_H
#define BCM2712_PCI_ASSIGNED_RANGE_H
#if !defined(ARM64_BOARD_CONFIG_BCM2712)
#error "CPU-translated PCI resource adaptation is restricted to BCM2712"
#endif
#include <IOKit/pci/IOPCIPrivate.h>
#include <IOKit/pci/IOPCIConfigurator.h>

/* Original allocator uses nextSubRange, including its non-null end sentinel,
 * as the allocation-list membership marker. A numeric start alone is NOT
 * allocation evidence: zero may be allocated, and nonzero may be unallocated.
 * This is family metadata only, never live hardware/memory-decode admission. */
static inline bool bcm2712_pci_range_assigned(const struct IOPCIRange *range)
{
    return range && range->nextSubRange && range->size && range->end >= range->start &&
        range->end - range->start == range->size;
}

static inline IOPCIAddressSpace bcm2712_pci_range_space(IOPCIAddressSpace space,
    const struct IOPCIRange *range)
{
    if ((range->type == kIOPCIResourceTypeMemory || range->type == kIOPCIResourceTypePrefetchMemory) &&
        (range->flags & kIOPCIRangeFlagBar64)) space.s.space = kIOPCI64BitMemorySpace;
    return space;
}
#endif
