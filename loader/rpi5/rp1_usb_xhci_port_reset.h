/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_PORT_RESET_H
#define RPI5_RP1_USB_XHCI_PORT_RESET_H

#include <stdint.h>

#include "rp1_usb_xhci_caps.h"

#define RPI5_XHCI_K65_ROOT_PORT 2u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_port_reset_io {
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
    void *context;
};

struct rpi5_xhci_port_reset_observation {
    uint32_t version, step;
    int32_t error;
    uint32_t port, portsc_offset;
    uint32_t command, status, before, reset_write, after, ack_write, final;
    uint32_t speed, link_state, reads, writes, polls, delayed_us;
};

/* Reset only controller 0 root port 2 while the xHCI controller is running.
 * The sole permitted write target is port 2 PORTSC. No other port, command,
 * runtime, doorbell, PCI, DMA or interrupt state is touched. */
int rpi5_rp1_xhci_reset_k65_port(const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_port_reset_io *,
    struct rpi5_xhci_port_reset_observation *);

#ifdef __cplusplus
}
#endif

#endif
