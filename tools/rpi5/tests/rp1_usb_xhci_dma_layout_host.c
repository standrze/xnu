/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "rp1_usb_xhci_dma_layout.h"

static int
overlap(struct rpi5_xhci_dma_span a, struct rpi5_xhci_dma_span b)
{
    return a.offset < b.offset + b.bytes && b.offset < a.offset + a.bytes;
}

int
main(void)
{
    const uint32_t raw[RPI5_RP1_XHCI_CAP_WORDS] = {
        0x01100020, 0x03000440, 0x140000f1, 0x07ff000a,
        0x0240fe6d, 0x00000500, 0x00000460, 0x0000002f,
    };
    struct rpi5_rp1_xhci_caps caps;
    assert(!rpi5_rp1_xhci_caps_decode(raw, &caps));
    struct rpi5_xhci_dma_layout layout, before;
    assert(!rpi5_rp1_xhci_dma_layout(&caps, 0xfffffe0100000000ull,
        0x80000000, RPI5_XHCI_DMA_ALLOCATION_BYTES, &layout));
    assert(layout.version == 1 && layout.context_bytes == 64);
    assert(layout.scratchpad_count == 64);
    assert(layout.dcbaa.bytes == 520 && layout.command_ring.offset == 0x1000);
    assert(layout.event_ring.offset == 0x2000 && layout.erst.offset == 0x3000);
    assert(layout.scratchpad_array.offset == 0x3040 &&
        layout.scratchpad_array.bytes == 512);
    for (unsigned i = 0; i < 64; i++) {
        assert(layout.scratchpad[i].offset == 0x4000 + i * 0x1000);
        assert(layout.scratchpad[i].bytes == 0x1000);
        if (i) assert(!overlap(layout.scratchpad[i - 1], layout.scratchpad[i]));
    }
    const struct rpi5_xhci_dma_span tail[] = {
        layout.device_context, layout.input_context, layout.endpoint0_ring,
        layout.keyboard_ring, layout.control_buffer, layout.keyboard_buffer,
    };
    for (unsigned i = 0; i < sizeof tail / sizeof tail[0]; i++) {
        assert(tail[i].offset + tail[i].bytes <= RPI5_XHCI_DMA_ALLOCATION_BYTES);
        if (i) assert(!overlap(tail[i - 1], tail[i]));
    }
    before = layout;
    caps.context_64 = 0;
    assert(rpi5_rp1_xhci_dma_layout(&caps, 0xfffffe0100000000ull,
        0x80000000, RPI5_XHCI_DMA_ALLOCATION_BYTES, &layout));
    assert(!memcmp(&layout, &before, sizeof layout));
    caps.context_64 = 1;
    assert(rpi5_rp1_xhci_dma_layout(&caps, 1, 0x80000000,
        RPI5_XHCI_DMA_ALLOCATION_BYTES, &layout));
    assert(rpi5_rp1_xhci_dma_layout(&caps, 0xfffffe0100000000ull,
        0x80000000, RPI5_XHCI_DMA_ALLOCATION_BYTES - 1, &layout));
    puts("RP1_XHCI_DMA_LAYOUT_PASS SCRATCH=64 CONTEXT=64 ALLOCATION=327680 NO_HARDWARE=1");
    return 0;
}
