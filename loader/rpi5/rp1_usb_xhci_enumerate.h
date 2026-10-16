/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_ENUMERATE_H
#define RPI5_RP1_USB_XHCI_ENUMERATE_H

#include <stdint.h>

#include "rp1_usb_xhci_noop.h"
#include "rp1_usb_xhci_port_reset.h"
#include "usb_hid_boot_descriptor.h"
#include "usb_xhci_control_transfer.h"
#include "usb_xhci_device_context.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_enumerate_io {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
    int (*dma_guard)(void *);
    int (*stage_address)(void *, uint8_t,
        struct rpi5_usb_xhci_address_device_plan *);
};

struct rpi5_xhci_enumerate_observation {
    uint32_t version, step;
    int32_t error;
    uint32_t reads, writes, polls, delayed_us, dma_checks;
    uint32_t operational_base, runtime_base, doorbell_base;
    uint32_t page_size, command_before, status_before, interrupt_before;
    uint32_t status_running, status_halted, command_halted;
    uint32_t event_index, event_type, completion_code, port_status_events;
    uint32_t left_running;
    uint8_t slot;
    struct rpi5_xhci_port_reset_observation port;
    struct rpi5_usb_xhci_address_device_plan address;
    struct rpi5_usb_boot_keyboard_identity keyboard;
};

/* Polling USB-4 runner. It starts from the exact passed USB-3 allocation and
 * register geometry, resets only root port 2, submits Enable Slot then Address
 * Device, submits the four prebuilt EP0 descriptor TDs, halts the controller,
 * and accepts only the strict K65 boot-keyboard identity. Interrupts remain
 * disabled. BME lease/release and watchdog recovery remain caller-owned. */
int rpi5_rp1_xhci_enumerate_k65(const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *, const struct rpi5_xhci_noop_image *,
    const struct rpi5_usb_xhci_enable_slot_plan *,
    const struct rpi5_usb_xhci_descriptor_batch *,
    const struct rpi5_xhci_enumerate_io *,
    struct rpi5_xhci_enumerate_observation *);

/* USB-5 continuation variant. It performs the identical enumeration and
 * identity checks but leaves the already-running controller intact so the
 * caller can stage and submit keyboard setup without a Run/Stop boundary. */
int rpi5_rp1_xhci_enumerate_k65_live(const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *, const struct rpi5_xhci_noop_image *,
    const struct rpi5_usb_xhci_enable_slot_plan *,
    const struct rpi5_usb_xhci_descriptor_batch *,
    const struct rpi5_xhci_enumerate_io *,
    struct rpi5_xhci_enumerate_observation *);

#ifdef __cplusplus
}
#endif

#endif
