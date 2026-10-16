/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_MAILBOX_FDT_H
#define RPI5_DISPLAY_MAILBOX_FDT_H
#include "fdt.h"

/* Explicit, narrow Pi5 platform profile; never a generic missing-property
 * default. The preserved Linux reference uses ARM64 direct DMA with no range
 * map on the mailbox controller. This is not a cache, buffer-ownership,
 * runtime-firmware or physical-address-to-bus-address proof for a caller. */
#define RPI5_MAILBOX_DMA_PI5_NO_RANGES_DIRECT 1u
#define RPI5_MAILBOX_PROP_ABSENT 0u
#define RPI5_MAILBOX_PROP_EMPTY 1u
struct rpi5_display_mailbox_fdt {
    struct rpi5_range mmio;
    uint64_t reg_bus_address, reg_bytes;
    uint64_t ranges_child, ranges_cpu, ranges_bytes;
    uint32_t fdt_bytes, fb_node, firmware_node, mailbox_node;
    uint32_t firmware_phandle, mailbox_phandle, dma_profile;
    uint32_t root_dma_ranges, soc_dma_ranges, mailbox_dma_ranges;
    uint32_t firmware_dma_ranges, linux_default_dma_mask_bits;
    uint32_t coherent_property_present, iommu_property_present;
};
/* Pure same-blob resolution, <=1MiB FDT. Requires a stable, readable entire
 * input for the duration of the call. Exact Pi5 root and a single supported
 * simple-bus parent, unique FB -> firmware -> mailbox chain, enabled paths,
 * explicit cell widths and one exact mailbox MMIO extent. Global phandles are
 * validated. Unsupported DMA/IOMMU/coherency/resource properties fail closed.
 * Caller must separately establish that this is the current boot's original
 * FDT and retain/revalidate its bytes; an old tree can pass this pure parser.
 * Output is disjoint from the whole input and unchanged on failure. No MMIO,
 * mailbox transaction, allocation, PA conversion, mapping or drawing occurs.
 */
int rpi5_display_mailbox_from_fdt(const void *buffer, size_t available,
    struct rpi5_display_mailbox_fdt *out);
#endif
