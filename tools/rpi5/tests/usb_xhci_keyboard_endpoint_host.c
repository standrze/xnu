/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_keyboard_endpoint.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct trb { uint64_t parameter; uint32_t status, control; };

static struct rpi5_rp1_xhci_caps
caps(void)
{
    struct rpi5_rp1_xhci_caps result = {0};
    result.interface_version = 0x110;
    result.capability_length = 0x20;
    result.max_slots = 64;
    result.max_interrupters = 4;
    result.max_ports = 3;
    result.max_scratchpad_buffers = 64;
    result.address_64 = 1;
    result.context_64 = 1;
    return result;
}

static struct rpi5_usb_boot_keyboard_identity
identity(void)
{
    return (struct rpi5_usb_boot_keyboard_identity){
        .vendor = RPI5_USB_K65_VENDOR,
        .product = RPI5_USB_K65_PRODUCT,
        .report_descriptor_bytes = 154,
        .endpoint_max_packet = 16,
        .configuration = 1,
        .interface = 0,
        .alternate = 0,
        .endpoint = 0x81,
        .interval = 4,
    };
}

int
main(void)
{
    static _Alignas(0x4000) uint8_t allocation[0x50000];
    memset(allocation, 0xa5, sizeof allocation);
    struct rpi5_rp1_xhci_caps capability = caps();
    struct rpi5_xhci_dma_layout layout;
    assert(!rpi5_rp1_xhci_dma_layout(&capability, (uint64_t)allocation,
        UINT64_C(0x1100000000), sizeof allocation, &layout));
    struct rpi5_usb_xhci_enable_slot_plan enable;
    struct rpi5_usb_xhci_address_device_plan address;
    assert(!rpi5_usb_xhci_enable_slot_plan(&layout, allocation,
        sizeof allocation, &enable));
    assert(!rpi5_usb_xhci_address_k65_plan(&layout, allocation,
        sizeof allocation, 5, &address));
    uint32_t *device = (uint32_t *)(allocation + 0x44000);
    device[0] = UINT32_C(0x08300000);
    device[1] = UINT32_C(0x00020000);
    device[2] = UINT32_C(0x12345678);
    device[3] = UINT32_C(0x10000001);
    device[4] = UINT32_C(0x87654321);

    struct rpi5_usb_boot_keyboard_identity keyboard = identity();
    struct rpi5_usb_xhci_keyboard_endpoint_plan endpoint;
    assert(!rpi5_usb_xhci_configure_k65_keyboard(&layout, allocation,
        sizeof allocation, &address, &keyboard, &endpoint));
    assert(endpoint.version == 1 && endpoint.slot == 5 &&
        endpoint.endpoint_id == 3 && endpoint.endpoint == 0x81 &&
        endpoint.max_packet == 16 && endpoint.interval == 4 &&
        endpoint.input_add_flags == 9 &&
        endpoint.slot_context0 == UINT32_C(0x18300000) &&
        endpoint.slot_context1 == UINT32_C(0x00020000) &&
        endpoint.slot_context3 == UINT32_C(0x10000001) &&
        endpoint.endpoint_context0 == UINT32_C(0x00030000) &&
        endpoint.endpoint_context1 == UINT32_C(0x0010003e) &&
        endpoint.endpoint_context4 == UINT32_C(0x00100008) &&
        endpoint.command_control == UINT32_C(0x05003001) &&
        endpoint.input_context_dma == UINT64_C(0x1100045000) &&
        endpoint.keyboard_ring_dma == UINT64_C(0x1100047000) &&
        endpoint.command_trb_dma == UINT64_C(0x1100001020));
    uint32_t *input = (uint32_t *)(allocation + 0x45000);
    assert(input[1] == 9 && input[16] == UINT32_C(0x18300000) &&
        input[17] == UINT32_C(0x00020000) &&
        input[18] == UINT32_C(0x12345678) &&
        input[19] == UINT32_C(0x10000001) &&
        input[20] == UINT32_C(0x87654321));
    assert(input[64] == UINT32_C(0x00030000) &&
        input[65] == UINT32_C(0x0010003e) &&
        input[66] == UINT32_C(0x00047001) && input[67] == 0x11 &&
        input[68] == UINT32_C(0x00100008));
    struct trb *commands = (struct trb *)(allocation + 0x1000);
    assert(commands[2].parameter == UINT64_C(0x1100045000) &&
        commands[2].control == UINT32_C(0x05003001));
    struct rpi5_usb_xhci_event_trb command_event = {
        endpoint.command_trb_dma, UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(33) << 10) | (UINT32_C(5) << 24),
    };
    assert(!rpi5_usb_xhci_configure_k65_complete(&endpoint,
        &command_event, 1));
    command_event.control ^= UINT32_C(1) << 24;
    assert(rpi5_usb_xhci_configure_k65_complete(&endpoint,
        &command_event, 1));

    struct rpi5_usb_xhci_keyboard_interrupt_plan interrupt;
    assert(!rpi5_usb_xhci_k65_interrupt_plan(&layout, allocation,
        sizeof allocation, &endpoint, &interrupt));
    assert(interrupt.version == 1 && interrupt.slot == 5 &&
        interrupt.endpoint_id == 3 && interrupt.endpoint == 0x81 &&
        interrupt.report_bytes == 8 && interrupt.trb_count == 1 &&
        interrupt.normal_control == UINT32_C(0x425) &&
        interrupt.link_control == UINT32_C(0x1803) &&
        interrupt.ring_dma == UINT64_C(0x1100047000) &&
        interrupt.report_dma == UINT64_C(0x1100049000) &&
        interrupt.link_trb_dma == UINT64_C(0x1100047ff0));
    struct trb *ring = (struct trb *)(allocation + 0x47000);
    assert(ring[0].parameter == interrupt.report_dma &&
        ring[0].status == 8 && ring[0].control == UINT32_C(0x425));
    assert(ring[255].parameter == interrupt.ring_dma &&
        ring[255].control == UINT32_C(0x1803));
    for (unsigned index = 0; index < 8; index++) {
        assert(allocation[0x49000 + index] == 0);
    }
    struct rpi5_usb_xhci_transfer_event transfer_event = {
        interrupt.normal_trb_dma, UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(32) << 10) | (UINT32_C(3) << 16) |
            (UINT32_C(5) << 24),
    };
    assert(!rpi5_usb_xhci_k65_interrupt_complete(&interrupt,
        &transfer_event, 1));
    transfer_event.status |= 1;
    assert(rpi5_usb_xhci_k65_interrupt_complete(&interrupt,
        &transfer_event, 1));

    struct rpi5_usb_xhci_keyboard_stream_plan stream;
    assert(!rpi5_usb_xhci_k65_stream_plan(&layout, allocation,
        sizeof allocation, &endpoint, &stream));
    assert(stream.version == 1 && stream.slot == 5 &&
        stream.endpoint_id == 3 && stream.report_bytes == 8 &&
        stream.report_count == 255 &&
        stream.normal_control == UINT32_C(0x425) &&
        stream.link_control == UINT32_C(0x1803) &&
        stream.first_trb_dma == UINT64_C(0x1100047000) &&
        stream.last_trb_dma == UINT64_C(0x1100047fe0) &&
        stream.link_trb_dma == UINT64_C(0x1100047ff0));
    for (unsigned index = 0; index < stream.report_count; index++) {
        assert(ring[index].parameter == stream.report_dma + index * 8 &&
            ring[index].status == 8 &&
            ring[index].control == UINT32_C(0x425));
    }
    assert(ring[255].parameter == stream.ring_dma &&
        ring[255].control == UINT32_C(0x1803));
    transfer_event = (struct rpi5_usb_xhci_transfer_event){
        stream.ring_dma + 17 * 16, UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(32) << 10) | (UINT32_C(3) << 16) |
            (UINT32_C(5) << 24),
    };
    assert(!rpi5_usb_xhci_k65_stream_complete(&stream, 17,
        &transfer_event, 1));
    assert(rpi5_usb_xhci_k65_stream_complete(&stream, 18,
        &transfer_event, 1));

    struct rpi5_usb_xhci_keyboard_endpoint_plan before;
    memset(&before, 0xa5, sizeof before); endpoint = before;
    keyboard.endpoint = 0x82;
    assert(rpi5_usb_xhci_configure_k65_keyboard(&layout, allocation,
        sizeof allocation, &address, &keyboard, &endpoint));
    assert(!memcmp(&before, &endpoint, sizeof before));
    puts("USB_XHCI_KEYBOARD_ENDPOINT_PASS SLOT=5 DCI=3 EP=81 "
        "PACKET=16 INTERVAL=4 REPORT=8 NO_MMIO NO_DMA");
    return 0;
}
