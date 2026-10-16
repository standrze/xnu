/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_keyboard_endpoint.h"

#include "usb_xhci_control_transfer.h"

#define CONTEXT_BYTES UINT32_C(64)
#define RING_BYTES UINT32_C(0x1000)
#define COMMAND_RING_BYTES UINT32_C(0x1000)
#define TRB_BYTES UINT32_C(16)
#define RING_TRBS (RING_BYTES / TRB_BYTES)
#define CONFIGURE_COMMAND_INDEX 2u
#define TRB_CYCLE UINT32_C(1)
#define TRB_TOGGLE_CYCLE UINT32_C(2)
#define TRB_ISP UINT32_C(1 << 2)
#define TRB_IOC UINT32_C(1 << 5)
#define TRB_TYPE_SHIFT 10u
#define TRB_TYPE_NORMAL 1u
#define TRB_TYPE_LINK 6u
#define TRB_TYPE_CONFIGURE_ENDPOINT 12u
#define TRB_TYPE_COMMAND_COMPLETION 33u
#define TRB_TYPE_TRANSFER_EVENT 32u
#define TRB_TYPE_MASK UINT32_C(0x3f)
#define COMPLETION_CODE_SUCCESS 1u
#define SLOT_SHIFT 24u
#define ENDPOINT_ID_SHIFT 16u
#define ENDPOINT_ID_MASK UINT32_C(0x1f)
#define INPUT_ADD_SLOT UINT32_C(1)
#define INPUT_ADD_KEYBOARD (UINT32_C(1) << RPI5_USB_K65_ENDPOINT_ID)
#define SLOT_CONTEXT_ENTRIES_SHIFT 27u
#define SLOT_CONTEXT_ENTRIES_MASK UINT32_C(0xf8000000)
#define SLOT_SPEED_HIGH 3u
#define SLOT_SPEED_SHIFT 20u
#define EP_TYPE_INTERRUPT_IN 7u
#define EP_TYPE_SHIFT 3u
#define EP_CERR_3 UINT32_C(3 << 1)
#define EP_MAX_PACKET_SHIFT 16u

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
        valid_span(&layout->command_ring, cpu, 0x1000, COMMAND_RING_BYTES) &&
        valid_span(&layout->device_context, cpu, 0x44000,
            32 * CONTEXT_BYTES) &&
        valid_span(&layout->input_context, cpu, 0x45000, 33 * CONTEXT_BYTES) &&
        valid_span(&layout->keyboard_ring, cpu, 0x47000, RING_BYTES) &&
        valid_span(&layout->keyboard_buffer, cpu, 0x49000, RING_BYTES);
}

static int
valid_identity(const struct rpi5_usb_boot_keyboard_identity *identity)
{
    return identity && identity->vendor == RPI5_USB_K65_VENDOR &&
        identity->product == RPI5_USB_K65_PRODUCT &&
        identity->configuration == 1 && identity->interface == 0 &&
        identity->alternate == 0 && identity->endpoint == 0x81 &&
        identity->endpoint_max_packet == 16 && identity->interval == 4 &&
        identity->report_descriptor_bytes == 154;
}

static void
zero(volatile uint8_t *bytes, uint32_t count)
{
    for (uint32_t index = 0; index < count; index++) bytes[index] = 0;
}

int
rpi5_usb_xhci_configure_k65_keyboard(
    const struct rpi5_xhci_dma_layout *layout, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_address_device_plan *address,
    const struct rpi5_usb_boot_keyboard_identity *identity,
    struct rpi5_usb_xhci_keyboard_endpoint_plan *output)
{
    if (!output || !valid_layout(layout, allocation, allocation_bytes) ||
        !address || address->version != 1 || !address->slot ||
        address->slot > 64 || address->root_port != 2 ||
        address->speed != SLOT_SPEED_HIGH ||
        address->input_context_dma != layout->input_context.dma ||
        !valid_identity(identity)) {
        return -1;
    }
    volatile uint8_t *base = allocation;
    volatile uint32_t *input = (volatile uint32_t *)(uintptr_t)(base +
        layout->input_context.offset);
    volatile const uint32_t *device =
        (volatile const uint32_t *)(uintptr_t)(base +
            layout->device_context.offset);
    volatile struct xhci_trb *commands =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->command_ring.offset);
    if (commands[1].parameter != address->input_context_dma ||
        commands[1].control != address->command_control ||
        commands[CONFIGURE_COMMAND_INDEX].parameter ||
        commands[CONFIGURE_COMMAND_INDEX].status ||
        commands[CONFIGURE_COMMAND_INDEX].control ||
        commands[RING_TRBS - 1].parameter != layout->command_ring.dma ||
        commands[RING_TRBS - 1].status ||
        commands[RING_TRBS - 1].control != address->link_control) {
        return -1;
    }

    const uint32_t device_slot0 = device[0];
    const uint32_t device_slot1 = device[1];
    const uint32_t device_slot3 = device[3];
    if (((device_slot0 >> SLOT_SPEED_SHIFT) & 0xf) != SLOT_SPEED_HIGH ||
        ((device_slot0 >> SLOT_CONTEXT_ENTRIES_SHIFT) & 0x1f) < 1 ||
        ((device_slot1 >> 16) & 0xff) != 2 ||
        !(device_slot3 & 0xff) || ((device_slot3 >> 27) & 0x1f) != 2) {
        return -1;
    }

    const uint32_t add_flags = INPUT_ADD_SLOT | INPUT_ADD_KEYBOARD;
    const uint32_t slot0 =
        (device_slot0 & ~SLOT_CONTEXT_ENTRIES_MASK) |
        (RPI5_USB_K65_ENDPOINT_ID << SLOT_CONTEXT_ENTRIES_SHIFT);
    const uint32_t endpoint0 = (identity->interval - 1u) << 16;
    const uint32_t endpoint1 =
        ((uint32_t)identity->endpoint_max_packet << EP_MAX_PACKET_SHIFT) |
        (EP_TYPE_INTERRUPT_IN << EP_TYPE_SHIFT) | EP_CERR_3;
    const uint32_t endpoint4 =
        ((uint32_t)identity->endpoint_max_packet << 16) |
        RPI5_USB_K65_REPORT_BYTES;
    const uint32_t command_control = TRB_CYCLE |
        (TRB_TYPE_CONFIGURE_ENDPOINT << TRB_TYPE_SHIFT) |
        ((uint32_t)address->slot << SLOT_SHIFT);

    zero((volatile uint8_t *)input, layout->input_context.bytes);
    input[1] = add_flags;
    volatile uint32_t *slot_context = input + CONTEXT_BYTES / 4;
    for (uint32_t index = 0; index < CONTEXT_BYTES / 4; index++) {
        slot_context[index] = device[index];
    }
    slot_context[0] = slot0;
    volatile uint32_t *keyboard = slot_context +
        RPI5_USB_K65_ENDPOINT_ID * (CONTEXT_BYTES / 4);
    keyboard[0] = endpoint0;
    keyboard[1] = endpoint1;
    keyboard[2] = (uint32_t)layout->keyboard_ring.dma | TRB_CYCLE;
    keyboard[3] = (uint32_t)(layout->keyboard_ring.dma >> 32);
    keyboard[4] = endpoint4;
    commands[CONFIGURE_COMMAND_INDEX].parameter = layout->input_context.dma;
    commands[CONFIGURE_COMMAND_INDEX].control = command_control;

    *output = (struct rpi5_usb_xhci_keyboard_endpoint_plan){
        .version = 1,
        .slot = address->slot,
        .endpoint_id = RPI5_USB_K65_ENDPOINT_ID,
        .endpoint = identity->endpoint,
        .max_packet = identity->endpoint_max_packet,
        .interval = identity->interval,
        .input_add_flags = add_flags,
        .slot_context0 = slot0,
        .slot_context1 = device_slot1,
        .slot_context3 = device_slot3,
        .endpoint_context0 = endpoint0,
        .endpoint_context1 = endpoint1,
        .endpoint_context4 = endpoint4,
        .command_control = command_control,
        .link_control = address->link_control,
        .input_context_dma = layout->input_context.dma,
        .keyboard_ring_dma = layout->keyboard_ring.dma,
        .command_trb_dma = layout->command_ring.dma +
            CONFIGURE_COMMAND_INDEX * TRB_BYTES,
        .link_trb_dma = layout->command_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
    };
    return 0;
}

int
rpi5_usb_xhci_configure_k65_complete(
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *plan,
    const struct rpi5_usb_xhci_event_trb *event, uint8_t expected_cycle)
{
    if (!plan || !event || plan->version != 1 || !plan->slot ||
        plan->slot > 64 || plan->endpoint_id != RPI5_USB_K65_ENDPOINT_ID ||
        expected_cycle > 1 || event->parameter != plan->command_trb_dma ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_COMMAND_COMPLETION ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS ||
        (event->control >> SLOT_SHIFT) != plan->slot) {
        return -1;
    }
    return 0;
}

int
rpi5_usb_xhci_k65_interrupt_plan(
    const struct rpi5_xhci_dma_layout *layout, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    struct rpi5_usb_xhci_keyboard_interrupt_plan *output)
{
    if (!output || !valid_layout(layout, allocation, allocation_bytes) ||
        !endpoint || endpoint->version != 1 || !endpoint->slot ||
        endpoint->slot > 64 || endpoint->endpoint_id !=
            RPI5_USB_K65_ENDPOINT_ID || endpoint->endpoint != 0x81 ||
        endpoint->max_packet != 16 || endpoint->interval != 4 ||
        endpoint->keyboard_ring_dma != layout->keyboard_ring.dma) {
        return -1;
    }
    volatile uint8_t *base = allocation;
    volatile struct xhci_trb *ring =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->keyboard_ring.offset);
    volatile uint8_t *report = base + layout->keyboard_buffer.offset;
    const uint32_t normal_control = TRB_CYCLE | TRB_ISP | TRB_IOC |
        (TRB_TYPE_NORMAL << TRB_TYPE_SHIFT);
    const uint32_t link_control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
        (TRB_TYPE_LINK << TRB_TYPE_SHIFT);
    zero((volatile uint8_t *)ring, layout->keyboard_ring.bytes);
    zero(report, RPI5_USB_K65_REPORT_BYTES);
    ring[0].parameter = layout->keyboard_buffer.dma;
    ring[0].status = RPI5_USB_K65_REPORT_BYTES;
    ring[0].control = normal_control;
    ring[RING_TRBS - 1].parameter = layout->keyboard_ring.dma;
    ring[RING_TRBS - 1].control = link_control;
    *output = (struct rpi5_usb_xhci_keyboard_interrupt_plan){
        .version = 1,
        .slot = endpoint->slot,
        .endpoint_id = RPI5_USB_K65_ENDPOINT_ID,
        .endpoint = 0x81,
        .report_bytes = RPI5_USB_K65_REPORT_BYTES,
        .trb_count = 1,
        .normal_control = normal_control,
        .link_control = link_control,
        .ring_dma = layout->keyboard_ring.dma,
        .report_dma = layout->keyboard_buffer.dma,
        .normal_trb_dma = layout->keyboard_ring.dma,
        .link_trb_dma = layout->keyboard_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
    };
    return 0;
}

int
rpi5_usb_xhci_k65_interrupt_complete(
    const struct rpi5_usb_xhci_keyboard_interrupt_plan *plan,
    const struct rpi5_usb_xhci_transfer_event *event, uint8_t expected_cycle)
{
    if (!plan || !event || plan->version != 1 || !plan->slot ||
        plan->slot > 64 || plan->endpoint_id != RPI5_USB_K65_ENDPOINT_ID ||
        plan->report_bytes != RPI5_USB_K65_REPORT_BYTES ||
        expected_cycle > 1 || event->parameter != plan->normal_trb_dma ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_TRANSFER_EVENT ||
        ((event->control >> ENDPOINT_ID_SHIFT) & ENDPOINT_ID_MASK) !=
            RPI5_USB_K65_ENDPOINT_ID ||
        (event->control >> SLOT_SHIFT) != plan->slot ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS ||
        (event->status & UINT32_C(0xffffff))) {
        return -1;
    }
    return 0;
}

int
rpi5_usb_xhci_k65_stream_plan(
    const struct rpi5_xhci_dma_layout *layout, void *allocation,
    uint32_t allocation_bytes,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    struct rpi5_usb_xhci_keyboard_stream_plan *output)
{
    if (!output || !valid_layout(layout, allocation, allocation_bytes) ||
        !endpoint || endpoint->version != 1 || !endpoint->slot ||
        endpoint->slot > 64 || endpoint->endpoint_id !=
            RPI5_USB_K65_ENDPOINT_ID || endpoint->endpoint != 0x81 ||
        endpoint->max_packet != 16 || endpoint->interval != 4 ||
        endpoint->keyboard_ring_dma != layout->keyboard_ring.dma ||
        RPI5_USB_K65_STREAM_REPORTS + 1 != RING_TRBS ||
        RPI5_USB_K65_STREAM_REPORTS * RPI5_USB_K65_REPORT_BYTES >
            layout->keyboard_buffer.bytes) {
        return -1;
    }
    volatile uint8_t *base = allocation;
    volatile struct xhci_trb *ring =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->keyboard_ring.offset);
    volatile uint8_t *reports = base + layout->keyboard_buffer.offset;
    const uint32_t normal_control = TRB_CYCLE | TRB_ISP | TRB_IOC |
        (TRB_TYPE_NORMAL << TRB_TYPE_SHIFT);
    const uint32_t link_control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
        (TRB_TYPE_LINK << TRB_TYPE_SHIFT);
    zero((volatile uint8_t *)ring, layout->keyboard_ring.bytes);
    zero(reports, layout->keyboard_buffer.bytes);
    for (uint32_t index = 0; index < RPI5_USB_K65_STREAM_REPORTS; index++) {
        ring[index].parameter = layout->keyboard_buffer.dma +
            (uint64_t)index * RPI5_USB_K65_REPORT_BYTES;
        ring[index].status = RPI5_USB_K65_REPORT_BYTES;
        ring[index].control = normal_control;
    }
    ring[RING_TRBS - 1].parameter = layout->keyboard_ring.dma;
    ring[RING_TRBS - 1].control = link_control;
    *output = (struct rpi5_usb_xhci_keyboard_stream_plan){
        .version = 1,
        .slot = endpoint->slot,
        .endpoint_id = RPI5_USB_K65_ENDPOINT_ID,
        .endpoint = 0x81,
        .report_bytes = RPI5_USB_K65_REPORT_BYTES,
        .report_count = RPI5_USB_K65_STREAM_REPORTS,
        .normal_control = normal_control,
        .link_control = link_control,
        .ring_dma = layout->keyboard_ring.dma,
        .report_dma = layout->keyboard_buffer.dma,
        .first_trb_dma = layout->keyboard_ring.dma,
        .last_trb_dma = layout->keyboard_ring.dma +
            (RPI5_USB_K65_STREAM_REPORTS - 1) * TRB_BYTES,
        .link_trb_dma = layout->keyboard_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
    };
    return 0;
}

int
rpi5_usb_xhci_k65_stream_complete(
    const struct rpi5_usb_xhci_keyboard_stream_plan *plan,
    uint32_t report_index, const struct rpi5_usb_xhci_transfer_event *event,
    uint8_t expected_cycle)
{
    if (!plan || !event || plan->version != 1 || !plan->slot ||
        plan->slot > 64 || plan->endpoint_id != RPI5_USB_K65_ENDPOINT_ID ||
        plan->report_bytes != RPI5_USB_K65_REPORT_BYTES ||
        plan->report_count != RPI5_USB_K65_STREAM_REPORTS ||
        report_index >= plan->report_count || expected_cycle > 1 ||
        event->parameter != plan->ring_dma +
            (uint64_t)report_index * TRB_BYTES ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_TRANSFER_EVENT ||
        ((event->control >> ENDPOINT_ID_SHIFT) & ENDPOINT_ID_MASK) !=
            RPI5_USB_K65_ENDPOINT_ID ||
        (event->control >> SLOT_SHIFT) != plan->slot ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS ||
        (event->status & UINT32_C(0xffffff))) {
        return -1;
    }
    return 0;
}
