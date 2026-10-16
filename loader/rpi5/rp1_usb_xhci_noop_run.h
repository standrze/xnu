/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_NOOP_RUN_H
#define RPI5_RP1_USB_XHCI_NOOP_RUN_H

#include <stdint.h>

#include "rp1_usb_xhci_noop.h"

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_xhci_noop_run_io {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*delay_us)(void *, uint32_t);
    int (*guard)(void *);
    /* Must freshly prove the retained allocation is the only admitted RP1
     * DMA target and PCI bus mastering is live for the exact endpoint. The
     * runner invokes it at bounded transition/event checkpoints; guard still
     * surrounds every individual MMIO and memory access. */
    int (*dma_guard)(void *);
};

struct rpi5_xhci_noop_run_observation {
    uint32_t step;
    int32_t error;
    uint32_t reads, writes, polls, delayed_us, dma_checks;
    uint32_t operational_base, runtime_base, doorbell_base;
    uint32_t page_size, command_before, status_before, interrupt_before;
    uint32_t command_running, status_running;
    uint64_t event_parameter;
    uint32_t event_status, event_control, completion_code, event_type;
    uint32_t port_status_events;
    uint32_t command_halted, status_halted;
};

/* Execute exactly one polling No-Op command. Interrupt enable remains clear;
 * no port or slot command is issued. The caller must have completed a fresh
 * halt/reset and initialized image in the same retained allocation. Any error
 * after RUN is written is terminal for this call and requires the independent
 * board watchdog/reset recovery path. */
int rpi5_rp1_xhci_run_noop(const struct rpi5_rp1_xhci_caps *,
    const struct rpi5_xhci_dma_layout *,
    const struct rpi5_xhci_noop_image *,
    const struct rpi5_xhci_noop_run_io *,
    struct rpi5_xhci_noop_run_observation *);

#ifdef __cplusplus
}
#endif

#endif
