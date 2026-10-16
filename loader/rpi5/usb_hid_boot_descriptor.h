/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_HID_BOOT_DESCRIPTOR_H
#define RPI5_USB_HID_BOOT_DESCRIPTOR_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RPI5_USB_K65_VENDOR UINT16_C(0x1b1c)
#define RPI5_USB_K65_PRODUCT UINT16_C(0x1baf)

struct rpi5_usb_boot_keyboard_identity {
    uint16_t vendor, product, usb_version, device_version;
    uint16_t configuration_bytes, report_descriptor_bytes;
    uint16_t endpoint_max_packet;
    uint8_t endpoint0_max_packet, configuration, interface, alternate;
    uint8_t endpoint, interval, interface_count;
};

/* Parse already-fetched standard descriptors and select only the K65's HID
 * boot-keyboard interface. This performs no transfer, allocation or I/O and
 * grants no authority over the two vendor HID interfaces. Output is unchanged
 * on failure; descriptor integers use USB little-endian byte order. */
int rpi5_usb_k65_boot_keyboard_identify(const uint8_t *device,
    size_t device_bytes, const uint8_t *configuration,
    size_t configuration_bytes, struct rpi5_usb_boot_keyboard_identity *);

#ifdef __cplusplus
}
#endif

#endif
