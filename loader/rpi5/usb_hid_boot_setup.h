/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_HID_BOOT_SETUP_H
#define RPI5_USB_HID_BOOT_SETUP_H

#include <stdint.h>

#include "usb_xhci_control_transfer.h"

#define RPI5_USB_K65_SETUP_TRANSFERS 3u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_usb_hid_boot_setup_transfer {
    uint64_t setup_packet, setup_trb_dma, status_trb_dma;
    uint32_t setup_control, status_control, trb_index;
};

struct rpi5_usb_hid_boot_setup_plan {
    uint32_t version, slot, transfer_count, trb_count, first_trb, link_control;
    uint32_t idle_duration;
    uint64_t ring_dma, link_trb_dma;
    struct rpi5_usb_hid_boot_setup_transfer
        transfer[RPI5_USB_K65_SETUP_TRANSFERS];
};

/* Build exactly SET_CONFIGURATION(1), SET_PROTOCOL(boot) and SET_IDLE(1) as
 * sequential no-data EP0 transfers. No other interface or class request can be
 * represented by this API. HID idle duration 1 requests a periodic report at
 * the protocol-defined 4-ms unit for a no-user-input physical probe. */
int rpi5_usb_k65_hid_boot_setup(const struct rpi5_xhci_dma_layout *,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    struct rpi5_usb_hid_boot_setup_plan *);

/* USB-6 uses duration zero so the device reports only state changes. Duration
 * one remains the USB-5 no-user-input probe. No other duration is admitted. */
int rpi5_usb_k65_hid_boot_setup_idle(const struct rpi5_xhci_dma_layout *,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    uint8_t idle_duration, struct rpi5_usb_hid_boot_setup_plan *);

int rpi5_usb_k65_hid_boot_setup_complete(
    const struct rpi5_usb_hid_boot_setup_plan *, uint32_t transfer_index,
    const struct rpi5_usb_xhci_transfer_event *, uint8_t expected_cycle);

#ifdef __cplusplus
}
#endif

#endif
