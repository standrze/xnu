/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_XHCI_DEVICE_CONTEXT_H
#define RPI5_USB_XHCI_DEVICE_CONTEXT_H

#include <stdint.h>

#include "rp1_usb_xhci_dma_layout.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_usb_xhci_enable_slot_plan {
    uint32_t version, trb_count, command_control, link_control;
    uint64_t command_trb_dma, link_trb_dma;
};

struct rpi5_usb_xhci_address_device_plan {
    uint32_t version, slot, root_port, speed, endpoint0_max_packet;
    uint32_t input_add_flags, slot_context0, slot_context1;
    uint32_t endpoint0_context1, command_control, link_control;
    uint64_t dcbaa_entry_dma, input_context_dma, device_context_dma;
    uint64_t endpoint0_ring_dma, command_trb_dma, link_trb_dma;
};

struct rpi5_usb_xhci_event_trb {
    uint64_t parameter;
    uint32_t status, control;
};

/* Build one Enable Slot command in the CPU-owned command ring. No device or
 * input context is published and no MMIO or DMA occurs. */
int rpi5_usb_xhci_enable_slot_plan(const struct rpi5_xhci_dma_layout *,
    void *allocation, uint32_t allocation_bytes,
    struct rpi5_usb_xhci_enable_slot_plan *);

/* Build the exact 64-byte input/device contexts and Address Device command for
 * one high-speed device on controller-0 root port 2. Slot comes only from a
 * separately validated successful Enable Slot completion and is bounded 1..64.
 * No command is submitted and no controller register is touched here. */
int rpi5_usb_xhci_address_k65_plan(const struct rpi5_xhci_dma_layout *,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    struct rpi5_usb_xhci_address_device_plan *);

/* Validate exact successful Command Completion Events. The Enable Slot parser
 * is the sole source of a slot number for the Address Device plan. */
int rpi5_usb_xhci_enable_slot_complete(
    const struct rpi5_usb_xhci_enable_slot_plan *,
    const struct rpi5_usb_xhci_event_trb *, uint8_t expected_cycle,
    uint8_t *slot);
int rpi5_usb_xhci_address_k65_complete(
    const struct rpi5_usb_xhci_address_device_plan *,
    const struct rpi5_usb_xhci_event_trb *, uint8_t expected_cycle);

#ifdef __cplusplus
}
#endif

#endif
