/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_NOOP_H
#define RPI5_RP1_USB_XHCI_NOOP_H

#include <stdint.h>

#include "rp1_usb_xhci_dma_layout.h"

#define RPI5_XHCI_TRB_BYTES 16u
#define RPI5_XHCI_COMMAND_TRBS 256u
#define RPI5_XHCI_EVENT_TRBS 256u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_noop_image {
    uint32_t version, bytes_zeroed, scratchpad_count, event_trbs;
    uint64_t dcbaa_dma, scratchpad_array_dma;
    uint64_t command_ring_dma, noop_trb_dma, link_trb_dma;
    uint64_t event_ring_dma, erst_dma;
    uint32_t noop_control, link_control, erst_size, reserved;
};

/* CPU-only image construction.  The allocation must be the exact retained
 * Normal-NC allocation described by layout.  This routine performs no MMIO,
 * cache maintenance, PCI configuration, bus-master enable or DMA. */
int rpi5_rp1_xhci_noop_image(const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *, void *allocation,
    uint32_t allocation_bytes, struct rpi5_xhci_noop_image *);

#ifdef __cplusplus
}
#endif

#endif
