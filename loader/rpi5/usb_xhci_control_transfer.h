/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_XHCI_CONTROL_TRANSFER_H
#define RPI5_USB_XHCI_CONTROL_TRANSFER_H

#include <stddef.h>
#include <stdint.h>

#include "rp1_usb_xhci_dma_layout.h"

#define RPI5_USB_DESCRIPTOR_DEVICE 1u
#define RPI5_USB_DESCRIPTOR_CONFIGURATION 2u
#define RPI5_USB_XHCI_CONTROL_TRBS 3u
#define RPI5_USB_K65_DESCRIPTOR_TRANSFERS 4u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_usb_xhci_control_plan {
    uint32_t version, descriptor_type, descriptor_bytes, trb_count;
    uint64_t setup_packet;
    uint64_t setup_trb_dma, data_trb_dma, status_trb_dma;
    uint64_t buffer_dma, link_trb_dma;
    uint32_t setup_control, data_control, status_control, link_control;
};

struct rpi5_usb_xhci_descriptor_transfer {
    uint32_t descriptor_type, descriptor_bytes, buffer_offset, trb_index;
    uint64_t buffer_dma, status_trb_dma;
};

struct rpi5_usb_xhci_descriptor_batch {
    uint32_t version, transfer_count, trb_count, link_control;
    uint64_t ring_dma, link_trb_dma;
    struct rpi5_usb_xhci_descriptor_transfer
        transfer[RPI5_USB_K65_DESCRIPTOR_TRANSFERS];
};

struct rpi5_usb_xhci_transfer_event {
    uint64_t parameter;
    uint32_t status, control;
};

/* Build one narrowly-scoped K65 GET_DESCRIPTOR transfer on the existing EP0
 * ring. This is a pure DMA-image operation: no MMIO, doorbell, BME, port,
 * command or device-context access is performed. The caller retains ownership
 * of the allocation and must publish it only after the normal DMA guards pass.
 * Output and allocation are unchanged on failure. */
int rpi5_usb_k65_get_descriptor_plan(
    const struct rpi5_xhci_dma_layout *, void *allocation,
    uint32_t allocation_bytes, uint8_t descriptor_type,
    uint16_t descriptor_bytes, struct rpi5_usb_xhci_control_plan *);

/* Build the exact four sequential K65 descriptor TDs in one EP0 ring. Each TD
 * has its own bounded buffer and IOC status TRB. */
int rpi5_usb_k65_descriptor_batch(const struct rpi5_xhci_dma_layout *,
    void *allocation, uint32_t allocation_bytes,
    struct rpi5_usb_xhci_descriptor_batch *);

/* Validate one successful endpoint-0 Transfer Event for the indexed TD. */
int rpi5_usb_k65_descriptor_complete(
    const struct rpi5_usb_xhci_descriptor_batch *, uint32_t transfer_index,
    const struct rpi5_usb_xhci_transfer_event *, uint8_t expected_cycle,
    uint8_t expected_slot);

#ifdef __cplusplus
}
#endif

#endif
