/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_BME_H
#define RPI5_RP1_USB_BME_H

#include <stdint.h>

#include "pcie_config.h"

#define RPI5_PCI_COMMAND_BUS_MASTER UINT16_C(0x0004)

#ifdef __cplusplus
extern "C" {
#endif

enum rpi5_rp1_usb_bme_state {
    RPI5_RP1_USB_BME_EMPTY,
    RPI5_RP1_USB_BME_ENABLING,
    RPI5_RP1_USB_BME_ENABLED,
    RPI5_RP1_USB_BME_DISABLING,
    RPI5_RP1_USB_BME_DISABLED,
    RPI5_RP1_USB_BME_QUARANTINED,
};

struct rpi5_rp1_usb_bme_io {
    void *context;
    int (*guard)(void *);
    int (*transfer)(void *, const struct rpi5_pcie_config_request *,
        uint32_t *);
};

struct rpi5_rp1_usb_bme {
    struct rpi5_rp1_usb_bme_io io;
    enum rpi5_rp1_usb_bme_state state;
    uint16_t original, enabled, current;
    uint32_t reads, writes, step;
    int32_t error;
};

/* Exact RP1 01:00.0 COMMAND bit-2 lease. No BAR, memory-enable, interrupt,
 * bridge or controller access. Any failure after a write quarantines the lease
 * and requires the independent watchdog/reset path; it is never guessed back. */
int rpi5_rp1_usb_bme_init(struct rpi5_rp1_usb_bme *,
    const struct rpi5_rp1_usb_bme_io *);
int rpi5_rp1_usb_bme_enable(struct rpi5_rp1_usb_bme *);
int rpi5_rp1_usb_bme_disable(struct rpi5_rp1_usb_bme *);
int rpi5_rp1_usb_bme_ready(struct rpi5_rp1_usb_bme *);

#ifdef __cplusplus
}
#endif

#endif
