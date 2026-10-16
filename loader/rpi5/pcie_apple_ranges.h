/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_APPLE_RANGES_H
#define RPI5_PCIE_APPLE_RANGES_H
#include "pcie_fdt.h"
#ifdef __cplusplus
extern "C" {
#endif

#define RPI5_RP1_BAR_COUNT 3
#define RPI5_PCI_RESERVED_MAX 8
struct rpi5_rp1_bar_candidate { uint64_t pci_base, size; };
struct rpi5_rp1_bar_candidates {
    struct rpi5_rp1_bar_candidate bar[RPI5_RP1_BAR_COUNT];
};
enum rpi5_apple_range_result {
    RPI5_APPLE_RANGE_OK=0, RPI5_APPLE_RANGE_ARGUMENT=-1,
    RPI5_APPLE_RANGE_PROFILE=-2, RPI5_APPLE_RANGE_NO_SPACE=-3,
    RPI5_APPLE_RANGE_INVARIANT=-4
};

/* Original Apple's IOPCIRange allocator plus a small fixed-RP1 policy adapter.
 * Pure proposal: three independent 32-bit nonprefetchable memory BARs, sizes
 * supplied by independently validated probing. Zero base is valid. One MEM32
 * outbound declaration; an optional PREFETCH64 window is validated but unused.
 * Up to eight occupied PCI-space half-open spans, never CPU physical resources.
 * Largest BAR first, no dynamic allocation, at most 11 upstream allocation
 * calls over private, bounded lists. Inputs/output must be disjoint and stable.
 *
 * No MMIO/config writes, BAR sizing, actual assignment, map, IRQ or DMA. Output
 * unchanged on failure. Never label a candidate assigned or enable decoding
 * from this result; actual provider ownership/programming/readbacks are still
 * required, then reconcile live BAR1 with rpi5_pcie_resource_plan. FDT's extra
 * hardware decode padding is NOT available for allocation. This component is
 * not included in BL33 or XNU. Whole IOPCIFamily compatibility is not claimed.
 */
int rpi5_apple_rp1_bar_candidates(const struct rpi5_pcie_window *outbound,
    uint32_t outbound_count, const uint64_t sizes[RPI5_RP1_BAR_COUNT],
    const struct rpi5_range *reserved_pci, uint32_t reserved_count,
    struct rpi5_rp1_bar_candidates *out);

#ifdef __cplusplus
}
#endif
#endif
