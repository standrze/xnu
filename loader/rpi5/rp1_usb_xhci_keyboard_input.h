/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_KEYBOARD_INPUT_H
#define RPI5_RP1_USB_XHCI_KEYBOARD_INPUT_H

#include <stdint.h>

#include "rp1_usb_xhci_enumerate.h"
#include "usb_hid_boot_keyboard.h"
#include "usb_hid_boot_setup.h"
#include "usb_xhci_keyboard_endpoint.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_keyboard_input_io {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
    int (*dma_guard)(void *);
};

struct rpi5_xhci_keyboard_input_observation {
    uint32_t version, step;
    int32_t error;
    uint32_t reads, writes, polls, delayed_us, dma_checks;
    uint32_t event_index, event_type, completion_code, port_status_events;
    uint64_t event_parameter;
    uint32_t event_status, event_control, transfer_index;
    uint32_t command_before, status_before, status_running;
    uint32_t status_halted, command_halted;
    uint8_t slot, endpoint_id;
    uint8_t report[RPI5_USB_HID_BOOT_REPORT_BYTES];
    uint8_t output[RPI5_USB_HID_BOOT_MAX_OUTPUT];
    uint32_t output_count;
};

/* Continue directly from a successful, halted USB-4 enumeration. Configure
 * only DCI 3, execute the three fixed EP0 setup requests, fetch one 8-byte
 * interrupt-IN report, halt, then decode it. Interrupts remain disabled; BME
 * lease/release and watchdog recovery remain caller-owned. */
int rpi5_rp1_xhci_k65_keyboard_input(
    const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *,
    const struct rpi5_xhci_enumerate_observation *,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *,
    const struct rpi5_usb_hid_boot_setup_plan *,
    const struct rpi5_usb_xhci_keyboard_interrupt_plan *,
    const struct rpi5_xhci_keyboard_input_io *,
    struct rpi5_xhci_keyboard_input_observation *);

#ifdef __cplusplus
}
#endif

#endif
