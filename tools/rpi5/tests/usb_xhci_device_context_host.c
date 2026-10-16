/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_device_context.h"

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
    assert(!rpi5_usb_xhci_enable_slot_plan(&layout, allocation,
        sizeof allocation, &enable));
    assert(enable.version == 1 && enable.trb_count == 1 &&
        enable.command_control == 0x2401 && enable.link_control == 0x1803 &&
        enable.command_trb_dma == UINT64_C(0x1100001000) &&
        enable.link_trb_dma == UINT64_C(0x1100001ff0));
    struct trb *commands = (struct trb *)(allocation + 0x1000);
    assert(commands[0].parameter == 0 && commands[0].status == 0 &&
        commands[0].control == 0x2401);
    assert(commands[255].parameter == UINT64_C(0x1100001000) &&
        commands[255].status == 0 && commands[255].control == 0x1803);
    struct rpi5_usb_xhci_event_trb event = {
        .parameter = enable.command_trb_dma,
        .status = UINT32_C(1 << 24),
        .control = UINT32_C(1) | (UINT32_C(33) << 10) |
            (UINT32_C(5) << 24),
    };
    uint8_t slot = 0xa5;
    assert(!rpi5_usb_xhci_enable_slot_complete(&enable, &event, 1, &slot));
    assert(slot == 5);
    event.status = UINT32_C(9 << 24); slot = 0xa5;
    assert(rpi5_usb_xhci_enable_slot_complete(&enable, &event, 1, &slot));
    assert(slot == 0xa5);
    event.status = UINT32_C(1 << 24);

    struct rpi5_usb_xhci_address_device_plan address;
    assert(!rpi5_usb_xhci_address_k65_plan(&layout, allocation,
        sizeof allocation, 5, &address));
    assert(address.version == 1 && address.slot == 5 &&
        address.root_port == 2 && address.speed == 3 &&
        address.endpoint0_max_packet == 64 && address.input_add_flags == 3 &&
        address.slot_context0 == 0x08300000 &&
        address.slot_context1 == 0x00020000 &&
        address.endpoint0_context1 == 0x00400026 &&
        address.command_control == 0x05002c01 &&
        address.link_control == 0x1803 &&
        address.dcbaa_entry_dma == UINT64_C(0x1100044000) &&
        address.input_context_dma == UINT64_C(0x1100045000) &&
        address.device_context_dma == UINT64_C(0x1100044000) &&
        address.endpoint0_ring_dma == UINT64_C(0x1100046000) &&
        address.command_trb_dma == UINT64_C(0x1100001010));
    uint64_t *dcbaa = (uint64_t *)allocation;
    assert(dcbaa[5] == UINT64_C(0x1100044000));
    uint32_t *input = (uint32_t *)(allocation + 0x45000);
    assert(input[0] == 0 && input[1] == 3);
    assert(input[16] == 0x08300000 && input[17] == 0x00020000);
    assert(input[33] == 0x00400026 &&
        input[34] == 0x00046001 && input[35] == 0x00000011 &&
        input[36] == 8);
    assert(commands[0].parameter == 0 && commands[0].status == 0 &&
        commands[0].control == 0x2401);
    assert(commands[1].parameter == UINT64_C(0x1100045000) &&
        commands[1].status == 0 && commands[1].control == 0x05002c01);
    event.parameter = address.command_trb_dma;
    assert(!rpi5_usb_xhci_address_k65_complete(&address, &event, 1));
    event.control = UINT32_C(1) | (UINT32_C(33) << 10) |
        (UINT32_C(6) << 24);
    assert(rpi5_usb_xhci_address_k65_complete(&address, &event, 1));

    struct rpi5_usb_xhci_address_device_plan before;
    memset(&before, 0xa5, sizeof before); address = before;
    assert(rpi5_usb_xhci_address_k65_plan(&layout, allocation,
        sizeof allocation, 0, &address));
    assert(!memcmp(&address, &before, sizeof address));
    assert(commands[0].control == 0x2401 &&
        commands[1].control == 0x05002c01 &&
        commands[255].control == 0x1803);
    puts("USB_XHCI_DEVICE_CONTEXT_PASS PORT=2 SPEED=HIGH SLOT=5 "
        "EP0=64 COMMANDS=ENABLE_SLOT,ADDRESS_DEVICE NO_MMIO NO_DMA");
    return 0;
}
