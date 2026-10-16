/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_LIFECYCLE_H
#define RPI5_RP1_USB_XHCI_LIFECYCLE_H

#include <stdint.h>

#include "rp1_usb_xhci_caps.h"

#define RPI5_XHCI_USBCMD_RUN_STOP UINT32_C(0x00000001)
#define RPI5_XHCI_USBCMD_HCRST UINT32_C(0x00000002)
#define RPI5_XHCI_USBSTS_HALTED UINT32_C(0x00000001)
#define RPI5_XHCI_USBSTS_FATAL UINT32_C(0x00000004)
#define RPI5_XHCI_USBSTS_CNR UINT32_C(0x00000800)

#ifdef __cplusplus
extern "C" {
#endif

/* The callbacks own register ordering and access validation. All offsets are
 * relative to the USB controller window. This bounded lifecycle touches only
 * USBCMD; it never writes USBSTS, port, doorbell, runtime, DMA pointer, or
 * interrupt registers. A successful reset leaves the controller halted and
 * not ready for DMA until a later owner installs all required data structures. */
struct rpi5_xhci_lifecycle_io {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
};

struct rpi5_xhci_lifecycle_observation {
    uint32_t step;
    int32_t error;
    uint32_t reads, writes, polls, delayed_us;
    uint32_t operational_base;
    uint32_t command_before, status_before;
    uint32_t halt_command, status_halted;
    uint32_t reset_command, command_after, status_after;
};

/* Run the halt/reset/ready sequence from xHCI 1.1 sections 4.2 and 5.4.
 * Capability words must already come from the exact stable read-only gate.
 * The observation always records the last completed action. Hardware writes
 * cannot be rolled back; any failure after the first write must be recovered
 * by the caller's independent watchdog/reset path. */
int rpi5_rp1_xhci_halt_reset(const uint32_t[RPI5_RP1_XHCI_CAP_WORDS],
    const struct rpi5_xhci_lifecycle_io *,
    struct rpi5_xhci_lifecycle_observation *);

#ifdef __cplusplus
}
#endif

#endif
