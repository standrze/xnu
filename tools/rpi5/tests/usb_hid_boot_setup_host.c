/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_setup.h"

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
    struct rpi5_usb_hid_boot_setup_plan plan;
    assert(!rpi5_usb_k65_hid_boot_setup(&layout, allocation,
        sizeof allocation, 5, &plan));
    assert(plan.version == 1 && plan.slot == 5 &&
        plan.transfer_count == 3 && plan.trb_count == 6 &&
        plan.first_trb == 12 && plan.idle_duration == 1 &&
        plan.ring_dma == UINT64_C(0x1100046000) &&
        plan.link_trb_dma == UINT64_C(0x1100046ff0) &&
        plan.link_control == UINT32_C(0x1803));
    static const uint64_t requests[3] = {
        UINT64_C(0x0000000000010900),
        UINT64_C(0x0000000000000b21),
        UINT64_C(0x0000000001000a21),
    };
    struct trb *ring = (struct trb *)(allocation + 0x46000);
    for (unsigned index = 0; index < 3; index++) {
        const unsigned trb = 12 + index * 2;
        assert(plan.transfer[index].setup_packet == requests[index] &&
            plan.transfer[index].trb_index == trb &&
            plan.transfer[index].setup_control == UINT32_C(0x851) &&
            plan.transfer[index].status_control == UINT32_C(0x11021));
        assert(ring[trb].parameter == requests[index] &&
            ring[trb].status == 8 && ring[trb].control == 0x851 &&
            ring[trb + 1].parameter == 0 && ring[trb + 1].status == 0 &&
            ring[trb + 1].control == 0x11021);
        struct rpi5_usb_xhci_transfer_event event = {
            plan.transfer[index].status_trb_dma, UINT32_C(1) << 24,
            UINT32_C(1) | (UINT32_C(32) << 10) |
                (UINT32_C(1) << 16) | (UINT32_C(5) << 24),
        };
        assert(!rpi5_usb_k65_hid_boot_setup_complete(&plan, index,
            &event, 1));
        event.control += UINT32_C(1) << 16;
        assert(rpi5_usb_k65_hid_boot_setup_complete(&plan, index,
            &event, 1));
    }
    assert(ring[255].parameter == plan.ring_dma &&
        ring[255].control == UINT32_C(0x1803));
    assert(!rpi5_usb_k65_hid_boot_setup_idle(&layout, allocation,
        sizeof allocation, 5, 0, &plan));
    assert(plan.idle_duration == 0 &&
        plan.transfer[2].setup_packet == UINT64_C(0x0000000000000a21) &&
        ring[16].parameter == UINT64_C(0x0000000000000a21));
    struct rpi5_usb_hid_boot_setup_plan before;
    memset(&before, 0xa5, sizeof before); plan = before;
    assert(rpi5_usb_k65_hid_boot_setup(&layout, allocation,
        sizeof allocation, 0, &plan));
    assert(!memcmp(&before, &plan, sizeof before));
    assert(rpi5_usb_k65_hid_boot_setup_idle(&layout, allocation,
        sizeof allocation, 5, 2, &plan));
    assert(!memcmp(&before, &plan, sizeof before));
    puts("USB_HID_BOOT_SETUP_PASS CONFIG=1 PROTOCOL=BOOT IDLE=1 "
        "INTERFACE=0 EP0_ONLY NO_MMIO NO_DMA");
    return 0;
}
