/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_descriptor.h"

#define USB_DEVICE_DESCRIPTOR 1u
#define USB_CONFIGURATION_DESCRIPTOR 2u
#define USB_INTERFACE_DESCRIPTOR 4u
#define USB_ENDPOINT_DESCRIPTOR 5u
#define USB_HID_DESCRIPTOR 0x21u
#define USB_REPORT_DESCRIPTOR 0x22u
#define USB_HID_CLASS 3u
#define USB_BOOT_SUBCLASS 1u
#define USB_KEYBOARD_PROTOCOL 1u
#define USB_ENDPOINT_IN 0x80u
#define USB_TRANSFER_INTERRUPT 3u

static uint16_t
le16(const uint8_t *bytes)
{
    return (uint16_t)(bytes[0] | (uint16_t)bytes[1] << 8);
}

int
rpi5_usb_k65_boot_keyboard_identify(const uint8_t *device,
    size_t device_bytes, const uint8_t *configuration,
    size_t configuration_bytes, struct rpi5_usb_boot_keyboard_identity *output)
{
    if (!device || !configuration || !output || device_bytes != 18 ||
        device[0] != 18 || device[1] != USB_DEVICE_DESCRIPTOR ||
        device[4] || device[5] || device[6] || device[7] != 64 ||
        le16(device + 8) != RPI5_USB_K65_VENDOR ||
        le16(device + 10) != RPI5_USB_K65_PRODUCT || device[17] != 1 ||
        configuration_bytes < 9 || configuration[0] != 9 ||
        configuration[1] != USB_CONFIGURATION_DESCRIPTOR ||
        le16(configuration + 2) != configuration_bytes ||
        configuration[4] != 3 || configuration[5] != 1 ||
        !(configuration[7] & 0x80) || configuration[8] > 250) {
        return -1;
    }

    struct rpi5_usb_boot_keyboard_identity result = {0};
    result.vendor = le16(device + 8);
    result.product = le16(device + 10);
    result.usb_version = le16(device + 2);
    result.device_version = le16(device + 12);
    result.endpoint0_max_packet = device[7];
    result.configuration_bytes = (uint16_t)configuration_bytes;
    result.configuration = configuration[5];
    result.interface_count = configuration[4];

    unsigned selected = 0, hid = 0, endpoint = 0;
    int current = -1;
    for (size_t offset = 0; offset < configuration_bytes;) {
        if (configuration_bytes - offset < 2) return -1;
        const uint8_t length = configuration[offset];
        const uint8_t type = configuration[offset + 1];
        if (length < 2 || length > configuration_bytes - offset) return -1;
        const uint8_t *descriptor = configuration + offset;
        if (type == USB_INTERFACE_DESCRIPTOR) {
            if (length != 9) return -1;
            current = descriptor[2];
            if (descriptor[5] == USB_HID_CLASS &&
                descriptor[6] == USB_BOOT_SUBCLASS &&
                descriptor[7] == USB_KEYBOARD_PROTOCOL) {
                if (selected || descriptor[2] != 0 || descriptor[3] != 0 ||
                    descriptor[4] != 1) return -1;
                selected = 1;
                result.interface = descriptor[2];
                result.alternate = descriptor[3];
            }
        } else if (type == USB_HID_DESCRIPTOR && current == 0) {
            if (!selected || hid || length != 9 || descriptor[2] != 0x00 ||
                descriptor[3] != 0x01 || descriptor[5] != 1 ||
                descriptor[6] != USB_REPORT_DESCRIPTOR ||
                le16(descriptor + 7) != 154) return -1;
            hid = 1;
            result.report_descriptor_bytes = le16(descriptor + 7);
        } else if (type == USB_ENDPOINT_DESCRIPTOR && current == 0) {
            if (!selected || !hid || endpoint || length != 7 ||
                descriptor[2] != (USB_ENDPOINT_IN | 1) ||
                (descriptor[3] & 3) != USB_TRANSFER_INTERRUPT ||
                le16(descriptor + 4) != 16 || descriptor[6] != 4) return -1;
            endpoint = 1;
            result.endpoint = descriptor[2];
            result.endpoint_max_packet = le16(descriptor + 4);
            result.interval = descriptor[6];
        }
        offset += length;
    }
    if (!selected || !hid || !endpoint) return -1;
    *output = result;
    return 0;
}
