/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_DMA_LAYOUT_H
#define RPI5_RP1_USB_XHCI_DMA_LAYOUT_H

#include <stdint.h>

#include "rp1_usb_xhci_caps.h"

#define RPI5_XHCI_DMA_ALLOCATION_BYTES UINT32_C(0x50000)
#define RPI5_XHCI_DMA_HOST_PAGE_BYTES UINT32_C(0x4000)
#define RPI5_XHCI_DMA_DEVICE_PAGE_BYTES UINT32_C(0x1000)
#define RPI5_XHCI_DMA_MAX_SCRATCHPADS 64u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_dma_span {
    uint64_t cpu, dma;
    uint32_t offset, bytes;
};

struct rpi5_xhci_dma_layout {
    uint32_t version, allocation_bytes, context_bytes, scratchpad_count;
    struct rpi5_xhci_dma_span dcbaa;
    struct rpi5_xhci_dma_span command_ring;
    struct rpi5_xhci_dma_span event_ring;
    struct rpi5_xhci_dma_span erst;
    struct rpi5_xhci_dma_span scratchpad_array;
    struct rpi5_xhci_dma_span scratchpad[RPI5_XHCI_DMA_MAX_SCRATCHPADS];
    struct rpi5_xhci_dma_span device_context;
    struct rpi5_xhci_dma_span input_context;
    struct rpi5_xhci_dma_span endpoint0_ring;
    struct rpi5_xhci_dma_span keyboard_ring;
    struct rpi5_xhci_dma_span control_buffer;
    struct rpi5_xhci_dma_span keyboard_buffer;
};

/* Pure layout only: no allocation, mapping, zeroing, register access or DMA.
 * The caller must own and retain one physically contiguous 0x50000-byte
 * Normal-NC allocation and independently prove the RP1 DMA translation. */
int rpi5_rp1_xhci_dma_layout(const struct rpi5_rp1_xhci_caps *,
    uint64_t cpu_base, uint64_t dma_base, uint32_t allocation_bytes,
    struct rpi5_xhci_dma_layout *);

#ifdef __cplusplus
}
#endif

#endif
