/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_dma_layout.h"

#include <stddef.h>

static int
span(uint64_t cpu, uint64_t dma, uint32_t offset, uint32_t bytes,
    struct rpi5_xhci_dma_span *out)
{
    if (!out || !bytes || offset > RPI5_XHCI_DMA_ALLOCATION_BYTES ||
        bytes > RPI5_XHCI_DMA_ALLOCATION_BYTES - offset ||
        cpu > UINT64_MAX - offset || dma > UINT64_MAX - offset) {
        return -1;
    }
    *out = (struct rpi5_xhci_dma_span){cpu + offset, dma + offset, offset, bytes};
    return 0;
}

int
rpi5_rp1_xhci_dma_layout(const struct rpi5_rp1_xhci_caps *caps,
    uint64_t cpu_base, uint64_t dma_base, uint32_t allocation_bytes,
    struct rpi5_xhci_dma_layout *out)
{
    if (!caps || !out || allocation_bytes != RPI5_XHCI_DMA_ALLOCATION_BYTES ||
        (cpu_base & (RPI5_XHCI_DMA_HOST_PAGE_BYTES - 1)) ||
        (dma_base & (RPI5_XHCI_DMA_HOST_PAGE_BYTES - 1)) ||
        cpu_base > UINT64_MAX - allocation_bytes ||
        dma_base > UINT64_MAX - allocation_bytes ||
        caps->interface_version != UINT32_C(0x110) ||
        caps->capability_length != 0x20 || !caps->address_64 ||
        !caps->context_64 || !caps->max_slots || caps->max_slots > 64 ||
        !caps->max_interrupters || caps->max_scratchpad_buffers >
            RPI5_XHCI_DMA_MAX_SCRATCHPADS) {
        return -1;
    }
    struct rpi5_xhci_dma_layout result = {
        .version = 1,
        .allocation_bytes = allocation_bytes,
        .context_bytes = 64,
        .scratchpad_count = caps->max_scratchpad_buffers,
    };
    if (span(cpu_base, dma_base, 0x0000, 65 * 8, &result.dcbaa) ||
        span(cpu_base, dma_base, 0x1000, 0x1000, &result.command_ring) ||
        span(cpu_base, dma_base, 0x2000, 0x1000, &result.event_ring) ||
        span(cpu_base, dma_base, 0x3000, 16, &result.erst) ||
        span(cpu_base, dma_base, 0x3040,
            caps->max_scratchpad_buffers * 8, &result.scratchpad_array)) {
        return -1;
    }
    for (uint32_t index = 0; index < caps->max_scratchpad_buffers; index++) {
        if (span(cpu_base, dma_base, 0x4000 + index * 0x1000,
                0x1000, &result.scratchpad[index])) {
            return -1;
        }
    }
    if (span(cpu_base, dma_base, 0x44000, 32 * 64,
            &result.device_context) ||
        span(cpu_base, dma_base, 0x45000, 33 * 64,
            &result.input_context) ||
        span(cpu_base, dma_base, 0x46000, 0x1000,
            &result.endpoint0_ring) ||
        span(cpu_base, dma_base, 0x47000, 0x1000,
            &result.keyboard_ring) ||
        span(cpu_base, dma_base, 0x48000, 0x1000,
            &result.control_buffer) ||
        span(cpu_base, dma_base, 0x49000, 0x1000,
            &result.keyboard_buffer)) {
        return -1;
    }
    *out = result;
    return 0;
}
