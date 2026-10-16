/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_device_context.h"

#include "rp1_usb_xhci_port_reset.h"

#include <stddef.h>

#define CONTEXT_BYTES UINT32_C(64)
#define COMMAND_RING_BYTES UINT32_C(0x1000)
#define TRB_BYTES UINT32_C(16)
#define COMMAND_TRBS (COMMAND_RING_BYTES / TRB_BYTES)
#define ADDRESS_COMMAND_INDEX 1u
#define TRB_CYCLE UINT32_C(1)
#define TRB_TOGGLE_CYCLE UINT32_C(2)
#define TRB_TYPE_SHIFT 10u
#define TRB_TYPE_LINK 6u
#define TRB_TYPE_ENABLE_SLOT 9u
#define TRB_TYPE_ADDRESS_DEVICE 11u
#define TRB_TYPE_COMMAND_COMPLETION 33u
#define TRB_TYPE_MASK UINT32_C(0x3f)
#define COMPLETION_CODE_SUCCESS 1u
#define SLOT_SHIFT 24u
#define SLOT_SPEED_HIGH 3u
#define SLOT_SPEED_SHIFT 20u
#define SLOT_CONTEXT_ENTRIES_SHIFT 27u
#define SLOT_ROOT_PORT_SHIFT 16u
#define EP_TYPE_CONTROL 4u
#define EP_TYPE_SHIFT 3u
#define EP_CERR_3 UINT32_C(3 << 1)
#define EP_MAX_PACKET_SHIFT 16u
#define EP0_MAX_PACKET 64u
#define INPUT_ADD_SLOT UINT32_C(1)
#define INPUT_ADD_EP0 UINT32_C(2)

struct xhci_trb {
    uint64_t parameter;
    uint32_t status, control;
};

_Static_assert(sizeof(struct xhci_trb) == TRB_BYTES, "xHCI TRB size");

static int
valid_span(const struct rpi5_xhci_dma_span *span, uint64_t cpu,
    uint32_t offset, uint32_t bytes)
{
    return span->offset == offset && span->bytes == bytes &&
        span->cpu == cpu + offset && !(span->dma & (TRB_BYTES - 1));
}

static int
valid_layout(const struct rpi5_xhci_dma_layout *layout, const void *allocation,
    uint32_t allocation_bytes)
{
    const uint64_t cpu = (uint64_t)(uintptr_t)allocation;
    return layout && allocation &&
        allocation_bytes == RPI5_XHCI_DMA_ALLOCATION_BYTES &&
        layout->version == 1 && layout->allocation_bytes == allocation_bytes &&
        layout->context_bytes == CONTEXT_BYTES && layout->scratchpad_count == 64 &&
        valid_span(&layout->dcbaa, cpu, 0, 65 * 8) &&
        valid_span(&layout->command_ring, cpu, 0x1000, COMMAND_RING_BYTES) &&
        valid_span(&layout->device_context, cpu, 0x44000, 32 * CONTEXT_BYTES) &&
        valid_span(&layout->input_context, cpu, 0x45000, 33 * CONTEXT_BYTES) &&
        valid_span(&layout->endpoint0_ring, cpu, 0x46000, 0x1000);
}

static void
zero(volatile uint8_t *bytes, uint32_t count)
{
    for (uint32_t index = 0; index < count; index++) bytes[index] = 0;
}

static uint32_t
link_ring(volatile struct xhci_trb *commands, uint64_t command_ring_dma)
{
    const uint32_t control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
        (TRB_TYPE_LINK << TRB_TYPE_SHIFT);
    commands[COMMAND_TRBS - 1].parameter = command_ring_dma;
    commands[COMMAND_TRBS - 1].control = control;
    return control;
}

int
rpi5_usb_xhci_enable_slot_plan(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes,
    struct rpi5_usb_xhci_enable_slot_plan *output)
{
    if (!output || !valid_layout(layout, allocation, allocation_bytes)) {
        return -1;
    }
    const uint32_t command_control = TRB_CYCLE |
        (TRB_TYPE_ENABLE_SLOT << TRB_TYPE_SHIFT);
    volatile uint8_t *base = allocation;
    volatile struct xhci_trb *commands =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->command_ring.offset);
    zero((volatile uint8_t *)commands, layout->command_ring.bytes);
    commands[0].control = command_control;
    const uint32_t link_control = link_ring(commands,
        layout->command_ring.dma);
    *output = (struct rpi5_usb_xhci_enable_slot_plan){
        .version = 1,
        .trb_count = 1,
        .command_control = command_control,
        .link_control = link_control,
        .command_trb_dma = layout->command_ring.dma,
        .link_trb_dma = layout->command_ring.dma +
            (COMMAND_TRBS - 1) * TRB_BYTES,
    };
    return 0;
}

int
rpi5_usb_xhci_address_k65_plan(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    struct rpi5_usb_xhci_address_device_plan *output)
{
    if (!output || slot == 0 || slot > 64 ||
        !valid_layout(layout, allocation, allocation_bytes)) {
        return -1;
    }
    volatile uint8_t *base = allocation;
    volatile uint64_t *dcbaa = (volatile uint64_t *)(uintptr_t)(base +
        layout->dcbaa.offset);
    volatile uint32_t *input = (volatile uint32_t *)(uintptr_t)(base +
        layout->input_context.offset);
    volatile uint8_t *device = base + layout->device_context.offset;
    volatile struct xhci_trb *commands =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->command_ring.offset);
    if (commands[0].parameter || commands[0].status ||
        commands[0].control != (TRB_CYCLE |
            (TRB_TYPE_ENABLE_SLOT << TRB_TYPE_SHIFT)) ||
        commands[ADDRESS_COMMAND_INDEX].parameter ||
        commands[ADDRESS_COMMAND_INDEX].status ||
        commands[ADDRESS_COMMAND_INDEX].control ||
        commands[COMMAND_TRBS - 1].parameter != layout->command_ring.dma ||
        commands[COMMAND_TRBS - 1].status ||
        commands[COMMAND_TRBS - 1].control != (TRB_CYCLE | TRB_TOGGLE_CYCLE |
            (TRB_TYPE_LINK << TRB_TYPE_SHIFT))) {
        return -1;
    }
    zero((volatile uint8_t *)input, layout->input_context.bytes);
    zero(device, layout->device_context.bytes);

    const uint32_t add_flags = INPUT_ADD_SLOT | INPUT_ADD_EP0;
    const uint32_t slot0 = (SLOT_SPEED_HIGH << SLOT_SPEED_SHIFT) |
        (UINT32_C(1) << SLOT_CONTEXT_ENTRIES_SHIFT);
    const uint32_t slot1 =
        RPI5_XHCI_K65_ROOT_PORT << SLOT_ROOT_PORT_SHIFT;
    const uint32_t endpoint1 = (EP0_MAX_PACKET << EP_MAX_PACKET_SHIFT) |
        (EP_TYPE_CONTROL << EP_TYPE_SHIFT) | EP_CERR_3;
    input[1] = add_flags;
    volatile uint32_t *slot_context = input + CONTEXT_BYTES / 4;
    slot_context[0] = slot0;
    slot_context[1] = slot1;
    volatile uint32_t *endpoint0 = slot_context + CONTEXT_BYTES / 4;
    endpoint0[1] = endpoint1;
    endpoint0[2] = (uint32_t)layout->endpoint0_ring.dma | TRB_CYCLE;
    endpoint0[3] = (uint32_t)(layout->endpoint0_ring.dma >> 32);
    endpoint0[4] = 8;
    dcbaa[slot] = layout->device_context.dma;

    const uint32_t command_control = TRB_CYCLE |
        (TRB_TYPE_ADDRESS_DEVICE << TRB_TYPE_SHIFT) |
        ((uint32_t)slot << SLOT_SHIFT);
    commands[ADDRESS_COMMAND_INDEX].parameter = layout->input_context.dma;
    commands[ADDRESS_COMMAND_INDEX].control = command_control;
    const uint32_t link_control = commands[COMMAND_TRBS - 1].control;
    *output = (struct rpi5_usb_xhci_address_device_plan){
        .version = 1,
        .slot = slot,
        .root_port = RPI5_XHCI_K65_ROOT_PORT,
        .speed = SLOT_SPEED_HIGH,
        .endpoint0_max_packet = EP0_MAX_PACKET,
        .input_add_flags = add_flags,
        .slot_context0 = slot0,
        .slot_context1 = slot1,
        .endpoint0_context1 = endpoint1,
        .command_control = command_control,
        .link_control = link_control,
        .dcbaa_entry_dma = layout->device_context.dma,
        .input_context_dma = layout->input_context.dma,
        .device_context_dma = layout->device_context.dma,
        .endpoint0_ring_dma = layout->endpoint0_ring.dma,
        .command_trb_dma = layout->command_ring.dma +
            ADDRESS_COMMAND_INDEX * TRB_BYTES,
        .link_trb_dma = layout->command_ring.dma +
            (COMMAND_TRBS - 1) * TRB_BYTES,
    };
    return 0;
}

static int
completion(const uint64_t command_trb_dma,
    const struct rpi5_usb_xhci_event_trb *event, uint8_t expected_cycle,
    uint8_t expected_slot, uint8_t *slot)
{
    if (!event || expected_cycle > 1 ||
        event->parameter != command_trb_dma ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_COMMAND_COMPLETION ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS) {
        return -1;
    }
    const uint8_t observed_slot = (uint8_t)(event->control >> SLOT_SHIFT);
    if (!observed_slot || observed_slot > 64 ||
        (expected_slot && observed_slot != expected_slot)) {
        return -1;
    }
    if (slot) *slot = observed_slot;
    return 0;
}

int
rpi5_usb_xhci_enable_slot_complete(
    const struct rpi5_usb_xhci_enable_slot_plan *plan,
    const struct rpi5_usb_xhci_event_trb *event, uint8_t expected_cycle,
    uint8_t *slot)
{
    if (!plan || !slot || plan->version != 1 || plan->trb_count != 1 ||
        plan->command_control != UINT32_C(0x2401)) {
        return -1;
    }
    uint8_t result;
    if (completion(plan->command_trb_dma, event, expected_cycle, 0,
            &result)) {
        return -1;
    }
    *slot = result;
    return 0;
}

int
rpi5_usb_xhci_address_k65_complete(
    const struct rpi5_usb_xhci_address_device_plan *plan,
    const struct rpi5_usb_xhci_event_trb *event, uint8_t expected_cycle)
{
    if (!plan || plan->version != 1 || !plan->slot || plan->slot > 64 ||
        plan->command_control != (TRB_CYCLE |
            (TRB_TYPE_ADDRESS_DEVICE << TRB_TYPE_SHIFT) |
            (plan->slot << SLOT_SHIFT))) {
        return -1;
    }
    return completion(plan->command_trb_dma, event, expected_cycle,
        (uint8_t)plan->slot, NULL);
}
