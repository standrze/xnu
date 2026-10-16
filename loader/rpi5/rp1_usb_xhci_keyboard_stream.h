/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_KEYBOARD_STREAM_H
#define RPI5_RP1_USB_XHCI_KEYBOARD_STREAM_H

#include <stdint.h>

#include "rp1_usb_xhci_enumerate.h"
#include "usb_hid_boot_keyboard.h"
#include "usb_hid_boot_setup.h"
#include "usb_xhci_keyboard_endpoint.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_keyboard_stream_io {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
    int (*dma_guard)(void *);
    int (*emit)(void *, const uint8_t *, uint32_t);
};

struct rpi5_xhci_keyboard_stream_state {
    uint32_t version, active, slot, endpoint_id;
    uint32_t event_index, event_cycle, report_index, report_cycle;
    uint32_t reports, output_bytes, port_status_events;
    struct rpi5_usb_hid_boot_keyboard keyboard;
};

struct rpi5_xhci_keyboard_stream_observation {
    uint32_t version, step;
    int32_t error;
    uint32_t reads, writes, polls, delayed_us, dma_checks;
    uint32_t event_index, event_cycle, event_type, completion_code;
    uint32_t report_index, report_cycle, reports, output_bytes;
    uint32_t port_status_events, setup_transfers;
    uint64_t event_parameter;
    uint32_t event_status, event_control;
    uint8_t report[RPI5_USB_HID_BOOT_REPORT_BYTES];
    uint8_t output[RPI5_USB_HID_BOOT_MAX_OUTPUT];
    uint32_t output_count;
};

/* Complete the three change-only HID setup transfers, configure DCI 3,
 * publish the cyclic report ring and return while the controller is running.
 * Interrupts stay disabled. The caller retains BME, watchdog and lifetime
 * ownership. */
int rpi5_rp1_xhci_k65_keyboard_stream_start(
    const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *,
    const struct rpi5_xhci_enumerate_observation *,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *,
    const struct rpi5_usb_hid_boot_setup_plan *,
    const struct rpi5_usb_xhci_keyboard_stream_plan *,
    const struct rpi5_xhci_keyboard_stream_io *,
    struct rpi5_xhci_keyboard_stream_state *,
    struct rpi5_xhci_keyboard_stream_observation *);

/* Poll at most one report without sleeping. Returns zero after consuming a
 * report, one when no report is ready, and minus one on a fail-closed error.
 * Complete decoded byte batches are passed to emit before decoder state and
 * the corresponding transfer TRB are committed for the next ring cycle. */
int rpi5_rp1_xhci_k65_keyboard_stream_poll(
    const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *,
    const struct rpi5_usb_xhci_keyboard_stream_plan *,
    const struct rpi5_xhci_keyboard_stream_io *,
    struct rpi5_xhci_keyboard_stream_state *,
    struct rpi5_xhci_keyboard_stream_observation *);

#ifdef __cplusplus
}
#endif

#endif
