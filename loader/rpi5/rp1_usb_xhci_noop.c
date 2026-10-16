/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_noop.h"

#include <stddef.h>

#define RPI5_XHCI_TRB_CYCLE UINT32_C(1)
#define RPI5_XHCI_TRB_TOGGLE_CYCLE UINT32_C(2)
#define RPI5_XHCI_TRB_TYPE_SHIFT 10u
#define RPI5_XHCI_TRB_TYPE_LINK 6u
#define RPI5_XHCI_TRB_TYPE_NOOP_COMMAND 23u

struct rpi5_xhci_trb {
    uint64_t parameter;
    uint32_t status, control;
};

struct rpi5_xhci_erst_entry {
    uint64_t ring_segment_base;
    uint32_t ring_segment_size, reserved;
};

static int
same_span(const struct rpi5_xhci_dma_span *left,
    const struct rpi5_xhci_dma_span *right)
{
    return left->cpu == right->cpu && left->dma == right->dma &&
        left->offset == right->offset && left->bytes == right->bytes;
}

static int
same_layout(const struct rpi5_xhci_dma_layout *left,
    const struct rpi5_xhci_dma_layout *right)
{
    if (left->version != right->version ||
        left->allocation_bytes != right->allocation_bytes ||
        left->context_bytes != right->context_bytes ||
        left->scratchpad_count != right->scratchpad_count ||
        !same_span(&left->dcbaa, &right->dcbaa) ||
        !same_span(&left->command_ring, &right->command_ring) ||
        !same_span(&left->event_ring, &right->event_ring) ||
        !same_span(&left->erst, &right->erst) ||
        !same_span(&left->scratchpad_array, &right->scratchpad_array) ||
        !same_span(&left->device_context, &right->device_context) ||
        !same_span(&left->input_context, &right->input_context) ||
        !same_span(&left->endpoint0_ring, &right->endpoint0_ring) ||
        !same_span(&left->keyboard_ring, &right->keyboard_ring) ||
        !same_span(&left->control_buffer, &right->control_buffer) ||
        !same_span(&left->keyboard_buffer, &right->keyboard_buffer)) {
        return 0;
    }
    for (uint32_t index = 0; index < left->scratchpad_count; index++) {
        if (!same_span(&left->scratchpad[index],
                &right->scratchpad[index])) {
            return 0;
        }
    }
    return 1;
}

int
rpi5_rp1_xhci_noop_image(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout, void *allocation,
    uint32_t allocation_bytes, struct rpi5_xhci_noop_image *out)
{
    if (!caps || !layout || !allocation || !out ||
        allocation_bytes != RPI5_XHCI_DMA_ALLOCATION_BYTES ||
        (uint64_t)allocation != layout->dcbaa.cpu - layout->dcbaa.offset) {
        return -1;
    }
    struct rpi5_xhci_dma_layout expected;
    if (rpi5_rp1_xhci_dma_layout(caps,
            (uint64_t)allocation, layout->dcbaa.dma,
            allocation_bytes, &expected) || !same_layout(layout, &expected)) {
        return -2;
    }

    volatile uint8_t *bytes = (volatile uint8_t *)allocation;
    for (uint32_t index = 0; index < allocation_bytes; index++) {
        bytes[index] = 0;
    }

    volatile uint64_t *dcbaa = (volatile uint64_t *)(uintptr_t)(
        bytes + layout->dcbaa.offset);
    dcbaa[0] = layout->scratchpad_array.dma;
    volatile uint64_t *scratchpads = (volatile uint64_t *)(uintptr_t)(
        bytes + layout->scratchpad_array.offset);
    for (uint32_t index = 0; index < layout->scratchpad_count; index++) {
        scratchpads[index] = layout->scratchpad[index].dma;
    }

    volatile struct rpi5_xhci_trb *commands =
        (volatile struct rpi5_xhci_trb *)(uintptr_t)(
            bytes + layout->command_ring.offset);
    uint32_t noop_control =
        (RPI5_XHCI_TRB_TYPE_NOOP_COMMAND << RPI5_XHCI_TRB_TYPE_SHIFT) |
        RPI5_XHCI_TRB_CYCLE;
    commands[0].control = noop_control;
    uint32_t link_control =
        (RPI5_XHCI_TRB_TYPE_LINK << RPI5_XHCI_TRB_TYPE_SHIFT) |
        RPI5_XHCI_TRB_TOGGLE_CYCLE | RPI5_XHCI_TRB_CYCLE;
    commands[RPI5_XHCI_COMMAND_TRBS - 1].parameter =
        layout->command_ring.dma;
    commands[RPI5_XHCI_COMMAND_TRBS - 1].control = link_control;

    volatile struct rpi5_xhci_erst_entry *erst =
        (volatile struct rpi5_xhci_erst_entry *)(uintptr_t)(
            bytes + layout->erst.offset);
    erst->ring_segment_base = layout->event_ring.dma;
    erst->ring_segment_size = RPI5_XHCI_EVENT_TRBS;

    struct rpi5_xhci_noop_image result = {
        .version = 1,
        .bytes_zeroed = allocation_bytes,
        .scratchpad_count = layout->scratchpad_count,
        .event_trbs = RPI5_XHCI_EVENT_TRBS,
        .dcbaa_dma = layout->dcbaa.dma,
        .scratchpad_array_dma = layout->scratchpad_array.dma,
        .command_ring_dma = layout->command_ring.dma,
        .noop_trb_dma = layout->command_ring.dma,
        .link_trb_dma = layout->command_ring.dma +
            (RPI5_XHCI_COMMAND_TRBS - 1) * RPI5_XHCI_TRB_BYTES,
        .event_ring_dma = layout->event_ring.dma,
        .erst_dma = layout->erst.dma,
        .noop_control = noop_control,
        .link_control = link_control,
        .erst_size = 1,
    };
    *out = result;
    return 0;
}
