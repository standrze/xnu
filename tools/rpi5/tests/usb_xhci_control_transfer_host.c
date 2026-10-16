/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_control_transfer.h"

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

    struct rpi5_usb_xhci_control_plan plan;
    assert(!rpi5_usb_k65_get_descriptor_plan(&layout, allocation,
        sizeof allocation, RPI5_USB_DESCRIPTOR_DEVICE, 8, &plan));
    assert(plan.version == 1 && plan.descriptor_type == 1 &&
        plan.descriptor_bytes == 8 && plan.trb_count == 3 &&
        plan.setup_packet == UINT64_C(0x0008000001000680) &&
        plan.setup_trb_dma == UINT64_C(0x1100046000) &&
        plan.data_trb_dma == UINT64_C(0x1100046010) &&
        plan.status_trb_dma == UINT64_C(0x1100046020) &&
        plan.buffer_dma == UINT64_C(0x1100048000) &&
        plan.link_trb_dma == UINT64_C(0x1100046ff0) &&
        plan.setup_control == UINT32_C(0x30851) &&
        plan.data_control == UINT32_C(0x10c15) &&
        plan.status_control == UINT32_C(0x1021) &&
        plan.link_control == UINT32_C(0x1803));
    struct trb *ring = (struct trb *)(allocation + 0x46000);
    assert(ring[0].parameter == plan.setup_packet && ring[0].status == 8 &&
        ring[0].control == plan.setup_control);
    assert(ring[1].parameter == plan.buffer_dma && ring[1].status == 8 &&
        ring[1].control == plan.data_control);
    assert(ring[2].parameter == 0 && ring[2].status == 0 &&
        ring[2].control == plan.status_control);
    assert(ring[255].parameter == plan.setup_trb_dma &&
        ring[255].status == 0 && ring[255].control == plan.link_control);
    for (unsigned index = 3; index < 255; index++) {
        assert(!ring[index].parameter && !ring[index].status &&
            !ring[index].control);
    }
    for (unsigned index = 0; index < 8; index++) {
        assert(allocation[0x48000 + index] == 0);
    }
    assert(allocation[0x48008] == 0xa5);

    assert(!rpi5_usb_k65_get_descriptor_plan(&layout, allocation,
        sizeof allocation, RPI5_USB_DESCRIPTOR_DEVICE, 18, &plan));
    assert(plan.setup_packet == UINT64_C(0x0012000001000680) &&
        ring[1].status == 18);
    assert(!rpi5_usb_k65_get_descriptor_plan(&layout, allocation,
        sizeof allocation, RPI5_USB_DESCRIPTOR_CONFIGURATION, 9, &plan));
    assert(plan.setup_packet == UINT64_C(0x0009000002000680) &&
        ring[1].status == 9);

    memset(allocation + 0x46000, 0x5a, 0x1000);
    struct rpi5_usb_xhci_control_plan before;
    memset(&before, 0xa5, sizeof before); plan = before;
    assert(rpi5_usb_k65_get_descriptor_plan(&layout, allocation,
        sizeof allocation, RPI5_USB_DESCRIPTOR_CONFIGURATION, 90, &plan));
    assert(!memcmp(&plan, &before, sizeof plan));
    for (unsigned index = 0; index < 0x1000; index++) {
        assert(allocation[0x46000 + index] == 0x5a);
    }

    assert(!rpi5_usb_k65_get_descriptor_plan(&layout, allocation,
        sizeof allocation, RPI5_USB_DESCRIPTOR_CONFIGURATION, 91, &plan));
    assert(plan.setup_packet == UINT64_C(0x005b000002000680) &&
        plan.descriptor_bytes == 91 && ring[1].status == 91);

    struct rpi5_usb_xhci_descriptor_batch batch;
    assert(!rpi5_usb_k65_descriptor_batch(&layout, allocation,
        sizeof allocation, &batch));
    assert(batch.version == 1 && batch.transfer_count == 4 &&
        batch.trb_count == 12 && batch.ring_dma == UINT64_C(0x1100046000) &&
        batch.link_trb_dma == UINT64_C(0x1100046ff0) &&
        batch.link_control == 0x1803);
    static const unsigned types[4] = {1, 1, 2, 2};
    static const unsigned sizes[4] = {8, 18, 9, 91};
    static const unsigned offsets[4] = {0, 0x40, 0x80, 0x100};
    for (unsigned index = 0; index < 4; index++) {
        const unsigned trb = index * 3;
        assert(batch.transfer[index].descriptor_type == types[index] &&
            batch.transfer[index].descriptor_bytes == sizes[index] &&
            batch.transfer[index].buffer_offset == offsets[index] &&
            batch.transfer[index].trb_index == trb &&
            batch.transfer[index].buffer_dma ==
                UINT64_C(0x1100048000) + offsets[index] &&
            batch.transfer[index].status_trb_dma ==
                UINT64_C(0x1100046000) + (trb + 2) * 16);
        assert(ring[trb].status == 8 && ring[trb].control == 0x30851 &&
            ring[trb + 1].parameter == batch.transfer[index].buffer_dma &&
            ring[trb + 1].status == sizes[index] &&
            ring[trb + 1].control == 0x10c15 &&
            ring[trb + 2].control == 0x1021);
    }
    struct rpi5_usb_xhci_transfer_event event = {
        .parameter = batch.transfer[0].status_trb_dma,
        .status = UINT32_C(1) << 24,
        .control = UINT32_C(1) | (UINT32_C(32) << 10) |
            (UINT32_C(1) << 16) | (UINT32_C(5) << 24),
    };
    assert(!rpi5_usb_k65_descriptor_complete(&batch, 0, &event, 1, 5));
    event.status |= 1;
    assert(rpi5_usb_k65_descriptor_complete(&batch, 0, &event, 1, 5));
    event.status = UINT32_C(1) << 24;
    event.parameter = batch.transfer[1].status_trb_dma;
    assert(!rpi5_usb_k65_descriptor_complete(&batch, 1, &event, 1, 5));
    puts("USB_XHCI_CONTROL_PASS GET_DESCRIPTOR=DEVICE8,18+CONFIG9,91 "
        "TRBS=12 EP0_ONLY NO_MMIO NO_DOORBELL NO_DMA");
    return 0;
}
