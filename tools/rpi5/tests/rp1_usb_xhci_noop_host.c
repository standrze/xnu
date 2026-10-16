/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_noop.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct trb { uint64_t parameter; uint32_t status, control; };
struct erst { uint64_t base; uint32_t size, reserved; };

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
    static _Alignas(0x4000) unsigned char allocation[0x50000];
    memset(allocation, 0xa5, sizeof(allocation));
    struct rpi5_rp1_xhci_caps capability = caps();
    struct rpi5_xhci_dma_layout layout;
    assert(!rpi5_rp1_xhci_dma_layout(&capability,
        (uint64_t)allocation, 0x1100000000, sizeof(allocation), &layout));
    struct rpi5_xhci_noop_image image, before;
    assert(!rpi5_rp1_xhci_noop_image(&capability, &layout, allocation,
        sizeof(allocation), &image));
    assert(image.bytes_zeroed == sizeof(allocation) &&
        image.scratchpad_count == 64 && image.event_trbs == 256 &&
        image.dcbaa_dma == 0x1100000000 &&
        image.command_ring_dma == 0x1100001000 &&
        image.noop_trb_dma == 0x1100001000 &&
        image.link_trb_dma == 0x1100001ff0 &&
        image.event_ring_dma == 0x1100002000 &&
        image.erst_dma == 0x1100003000 && image.noop_control == 0x5c01 &&
        image.link_control == 0x1803 && image.erst_size == 1);
    uint64_t *dcbaa = (uint64_t *)(allocation + layout.dcbaa.offset);
    uint64_t *scratchpads = (uint64_t *)(
        allocation + layout.scratchpad_array.offset);
    assert(dcbaa[0] == 0x1100003040 && dcbaa[1] == 0);
    for (unsigned index = 0; index < 64; index++) {
        assert(scratchpads[index] == 0x1100004000 + index * 0x1000);
    }
    struct trb *commands = (struct trb *)(
        allocation + layout.command_ring.offset);
    assert(commands[0].parameter == 0 && commands[0].status == 0 &&
        commands[0].control == 0x5c01);
    assert(commands[255].parameter == 0x1100001000 &&
        commands[255].status == 0 && commands[255].control == 0x1803);
    struct erst *entry = (struct erst *)(allocation + layout.erst.offset);
    assert(entry->base == 0x1100002000 && entry->size == 256 &&
        entry->reserved == 0);
    for (unsigned index = 0; index < sizeof(allocation); index++) {
        int expected = (index < 8) ||
            (index >= 0x3040 && index < 0x3240) ||
            (index >= 0x1000 && index < 0x1010) ||
            (index >= 0x1ff0 && index < 0x2000) ||
            (index >= 0x3000 && index < 0x3010);
        if (!expected) assert(allocation[index] == 0);
    }

    memset(&image, 0xa5, sizeof(image)); before = image;
    struct rpi5_xhci_dma_layout changed = layout;
    changed.keyboard_buffer.dma++;
    assert(rpi5_rp1_xhci_noop_image(&capability, &changed, allocation,
        sizeof(allocation), &image));
    assert(!memcmp(&image, &before, sizeof(image)));
    capability.address_64 = 0;
    assert(rpi5_rp1_xhci_noop_image(&capability, &layout, allocation,
        sizeof(allocation), &image));
    assert(!memcmp(&image, &before, sizeof(image)));
    printf("XHCI_NOOP_IMAGE_PASS scratchpads=64 event_trbs=256 "
        "NO_MMIO NO_BME NO_DMA\n");
    return 0;
}
