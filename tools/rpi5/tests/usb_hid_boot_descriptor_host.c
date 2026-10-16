/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_descriptor.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static const uint8_t device[18] = {
    18,1,0x00,0x02,0,0,0,64,0x1c,0x1b,0xaf,0x1b,0x12,0x00,1,2,3,1
};

static const uint8_t configuration[91] = {
    9,2,91,0,3,1,0,0xa0,250,
    9,4,0,0,1,3,1,1,0,
    9,0x21,0x00,0x01,0,1,0x22,154,0,
    7,5,0x81,3,16,0,4,
    9,4,1,0,2,3,0,0,0,
    9,0x21,0x00,0x01,0,1,0x22,29,0,
    7,5,0x82,3,0,4,4,
    7,5,0x01,3,0,4,4,
    9,4,2,0,1,3,0,0,0,
    9,0x21,0x00,0x01,0,1,0x22,21,0,
    7,5,0x83,3,64,0,4,
};

static void rejected_configuration(unsigned index, uint8_t value)
{
    uint8_t changed[sizeof configuration];
    memcpy(changed, configuration, sizeof changed);
    changed[index] = value;
    struct rpi5_usb_boot_keyboard_identity before, out;
    memset(&before, 0xa5, sizeof before); out = before;
    assert(rpi5_usb_k65_boot_keyboard_identify(device, sizeof device,
        changed, sizeof changed, &out));
    assert(!memcmp(&before, &out, sizeof out));
}

static void rejected_device(unsigned index, uint8_t value)
{
    uint8_t changed[sizeof device];
    memcpy(changed, device, sizeof changed);
    changed[index] = value;
    struct rpi5_usb_boot_keyboard_identity before, out;
    memset(&before, 0xa5, sizeof before); out = before;
    assert(rpi5_usb_k65_boot_keyboard_identify(changed, sizeof changed,
        configuration, sizeof configuration, &out));
    assert(!memcmp(&before, &out, sizeof out));
}

int main(void)
{
    struct rpi5_usb_boot_keyboard_identity out;
    memset(&out, 0xa5, sizeof out);
    assert(!rpi5_usb_k65_boot_keyboard_identify(device, sizeof device,
        configuration, sizeof configuration, &out));
    assert(out.vendor == 0x1b1c && out.product == 0x1baf &&
        out.usb_version == 0x0200 && out.device_version == 0x0012 &&
        out.endpoint0_max_packet == 64 && out.configuration_bytes == 91 &&
        out.configuration == 1 && out.interface_count == 3 &&
        out.interface == 0 && out.alternate == 0 && out.endpoint == 0x81 &&
        out.endpoint_max_packet == 16 && out.interval == 4 &&
        out.report_descriptor_bytes == 154);
    rejected_device(10, 0);          /* Product ID. */
    rejected_configuration(15, 0);   /* Boot subclass. */
    rejected_configuration(16, 0);   /* Keyboard protocol. */
    rejected_configuration(29, 0x82);/* Endpoint address. */
    rejected_configuration(31, 8);   /* Endpoint max packet. */
    rejected_configuration(13, 0);   /* Interface endpoint count. */
    rejected_configuration(2, 90);   /* Configuration extent. */
    puts("USB_K65_DESCRIPTOR_PASS INTERFACE=0 ENDPOINT=81 PACKET=16 VENDOR_INTERFACES_IGNORED=2 NO_IO=1");
    return 0;
}
