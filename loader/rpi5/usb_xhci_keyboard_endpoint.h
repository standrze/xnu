/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_XHCI_KEYBOARD_ENDPOINT_H
#define RPI5_USB_XHCI_KEYBOARD_ENDPOINT_H

#include <stdint.h>

#include "usb_hid_boot_descriptor.h"
#include "usb_xhci_control_transfer.h"
#include "usb_xhci_device_context.h"

#define RPI5_USB_K65_ENDPOINT_ID 3u
#define RPI5_USB_K65_REPORT_BYTES 8u
#define RPI5_USB_K65_STREAM_REPORTS 255u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_usb_xhci_keyboard_endpoint_plan {
    uint32_t version, slot, endpoint_id, endpoint, max_packet, interval;
    uint32_t input_add_flags, slot_context0, slot_context1, slot_context3;
    uint32_t endpoint_context0, endpoint_context1, endpoint_context4;
    uint32_t command_control, link_control;
    uint64_t input_context_dma, keyboard_ring_dma;
    uint64_t command_trb_dma, link_trb_dma;
};

struct rpi5_usb_xhci_keyboard_interrupt_plan {
    uint32_t version, slot, endpoint_id, endpoint, report_bytes, trb_count;
    uint32_t normal_control, link_control;
    uint64_t ring_dma, report_dma, normal_trb_dma, link_trb_dma;
};

struct rpi5_usb_xhci_keyboard_stream_plan {
    uint32_t version, slot, endpoint_id, endpoint, report_bytes;
    uint32_t report_count, normal_control, link_control;
    uint64_t ring_dma, report_dma, first_trb_dma, last_trb_dma;
    uint64_t link_trb_dma;
};

/* Build only the Configure Endpoint input context and command for the already
 * identified K65 interface-0 interrupt-IN endpoint. The slot must come from a
 * separately validated Address Device plan. No MMIO or DMA occurs here. */
int rpi5_usb_xhci_configure_k65_keyboard(
    const struct rpi5_xhci_dma_layout *, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_address_device_plan *,
    const struct rpi5_usb_boot_keyboard_identity *,
    struct rpi5_usb_xhci_keyboard_endpoint_plan *);

int rpi5_usb_xhci_configure_k65_complete(
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *,
    const struct rpi5_usb_xhci_event_trb *, uint8_t expected_cycle);

/* Build one 8-byte Normal TRB on DCI 3's private ring. The report buffer and
 * ring are cleared first; output and allocation are unchanged on failure. */
int rpi5_usb_xhci_k65_interrupt_plan(
    const struct rpi5_xhci_dma_layout *, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *,
    struct rpi5_usb_xhci_keyboard_interrupt_plan *);

/* Validate one exact successful DCI-3 Transfer Event. */
int rpi5_usb_xhci_k65_interrupt_complete(
    const struct rpi5_usb_xhci_keyboard_interrupt_plan *,
    const struct rpi5_usb_xhci_transfer_event *, uint8_t expected_cycle);

/* Build the full DCI-3 transfer ring as 255 independent 8-byte reports plus
 * its cycle-toggling Link TRB. Each report has a disjoint DMA buffer. A
 * consumer may re-publish a completed TRB with the opposite cycle bit before
 * the controller returns to it, allowing bounded polling without interrupts. */
int rpi5_usb_xhci_k65_stream_plan(
    const struct rpi5_xhci_dma_layout *, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *,
    struct rpi5_usb_xhci_keyboard_stream_plan *);

int rpi5_usb_xhci_k65_stream_complete(
    const struct rpi5_usb_xhci_keyboard_stream_plan *, uint32_t report_index,
    const struct rpi5_usb_xhci_transfer_event *, uint8_t expected_cycle);

#ifdef __cplusplus
}
#endif

#endif
