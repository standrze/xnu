/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_xhci_control_transfer.h"

#define TRB_CYCLE UINT32_C(1)
#define TRB_TOGGLE_CYCLE UINT32_C(2)
#define TRB_CHAIN UINT32_C(1 << 4)
#define TRB_IOC UINT32_C(1 << 5)
#define TRB_IDT UINT32_C(1 << 6)
#define TRB_ISP UINT32_C(1 << 2)
#define TRB_DIR_IN UINT32_C(1 << 16)
#define TRB_TYPE_SHIFT 10u
#define TRB_TYPE_SETUP 2u
#define TRB_TYPE_DATA 3u
#define TRB_TYPE_STATUS 4u
#define TRB_TYPE_LINK 6u
#define TRB_TRT_IN UINT32_C(3 << 16)
#define USB_REQUEST_GET_DESCRIPTOR 6u
#define USB_REQUEST_TYPE_DEVICE_IN 0x80u
#define EP0_RING_BYTES UINT32_C(0x1000)
#define CONTROL_BUFFER_BYTES UINT32_C(0x1000)
#define TRB_BYTES UINT32_C(16)
#define RING_TRBS (EP0_RING_BYTES / TRB_BYTES)
#define TRB_TYPE_TRANSFER_EVENT 32u
#define TRB_TYPE_MASK UINT32_C(0x3f)
#define COMPLETION_CODE_SUCCESS 1u
#define ENDPOINT_ID_SHIFT 16u
#define ENDPOINT_ID_MASK UINT32_C(0x1f)
#define SLOT_ID_SHIFT 24u

struct xhci_trb {
    uint64_t parameter;
    uint32_t status, control;
};

_Static_assert(sizeof(struct xhci_trb) == TRB_BYTES, "xHCI TRB size");

static int
valid_request(uint8_t type, uint16_t bytes)
{
    return (type == RPI5_USB_DESCRIPTOR_DEVICE &&
            (bytes == 8 || bytes == 18)) ||
        (type == RPI5_USB_DESCRIPTOR_CONFIGURATION &&
            (bytes == 9 || bytes == 91));
}

static int
valid_layout(const struct rpi5_xhci_dma_layout *layout, const void *allocation,
    uint32_t allocation_bytes, uint16_t descriptor_bytes)
{
    const uint64_t cpu = (uint64_t)(uintptr_t)allocation;
    return layout && allocation &&
        allocation_bytes == RPI5_XHCI_DMA_ALLOCATION_BYTES &&
        layout->version == 1 && layout->allocation_bytes == allocation_bytes &&
        layout->context_bytes == 64 && layout->scratchpad_count == 64 &&
        layout->endpoint0_ring.offset == UINT32_C(0x46000) &&
        layout->endpoint0_ring.bytes == EP0_RING_BYTES &&
        layout->control_buffer.offset == UINT32_C(0x48000) &&
        layout->control_buffer.bytes == CONTROL_BUFFER_BYTES &&
        layout->endpoint0_ring.cpu == cpu + layout->endpoint0_ring.offset &&
        layout->control_buffer.cpu == cpu + layout->control_buffer.offset &&
        !(layout->endpoint0_ring.dma & (TRB_BYTES - 1)) &&
        !(layout->control_buffer.dma & (TRB_BYTES - 1)) &&
        descriptor_bytes <= layout->control_buffer.bytes;
}

int
rpi5_usb_k65_get_descriptor_plan(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes, uint8_t descriptor_type,
    uint16_t descriptor_bytes, struct rpi5_usb_xhci_control_plan *output)
{
    if (!output || !valid_request(descriptor_type, descriptor_bytes) ||
        !valid_layout(layout, allocation, allocation_bytes, descriptor_bytes)) {
        return -1;
    }

    const uint64_t setup = (uint64_t)USB_REQUEST_TYPE_DEVICE_IN |
        ((uint64_t)USB_REQUEST_GET_DESCRIPTOR << 8) |
        ((uint64_t)descriptor_type << 24) |
        ((uint64_t)descriptor_bytes << 48);
    const uint32_t setup_control = TRB_CYCLE | TRB_CHAIN | TRB_IDT |
        (TRB_TYPE_SETUP << TRB_TYPE_SHIFT) | TRB_TRT_IN;
    const uint32_t data_control = TRB_CYCLE | TRB_CHAIN | TRB_ISP |
        (TRB_TYPE_DATA << TRB_TYPE_SHIFT) | TRB_DIR_IN;
    const uint32_t status_control = TRB_CYCLE | TRB_IOC |
        (TRB_TYPE_STATUS << TRB_TYPE_SHIFT);
    const uint32_t link_control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
        (TRB_TYPE_LINK << TRB_TYPE_SHIFT);

    struct rpi5_usb_xhci_control_plan result = {
        .version = 1,
        .descriptor_type = descriptor_type,
        .descriptor_bytes = descriptor_bytes,
        .trb_count = RPI5_USB_XHCI_CONTROL_TRBS,
        .setup_packet = setup,
        .setup_trb_dma = layout->endpoint0_ring.dma,
        .data_trb_dma = layout->endpoint0_ring.dma + TRB_BYTES,
        .status_trb_dma = layout->endpoint0_ring.dma + 2 * TRB_BYTES,
        .buffer_dma = layout->control_buffer.dma,
        .link_trb_dma = layout->endpoint0_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
        .setup_control = setup_control,
        .data_control = data_control,
        .status_control = status_control,
        .link_control = link_control,
    };

    volatile uint8_t *base = (volatile uint8_t *)allocation;
    volatile struct xhci_trb *ring =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->endpoint0_ring.offset);
    volatile uint8_t *buffer = base + layout->control_buffer.offset;
    for (uint32_t index = 0; index < EP0_RING_BYTES; index++) {
        ((volatile uint8_t *)ring)[index] = 0;
    }
    for (uint32_t index = 0; index < descriptor_bytes; index++) {
        buffer[index] = 0;
    }
    ring[0].parameter = setup;
    ring[0].status = 8;
    ring[0].control = setup_control;
    ring[1].parameter = layout->control_buffer.dma;
    ring[1].status = descriptor_bytes;
    ring[1].control = data_control;
    ring[2].control = status_control;
    ring[RING_TRBS - 1].parameter = layout->endpoint0_ring.dma;
    ring[RING_TRBS - 1].control = link_control;
    *output = result;
    return 0;
}

static void
write_descriptor(volatile struct xhci_trb *ring, uint32_t trb_index,
    uint64_t buffer_dma, uint8_t descriptor_type, uint16_t descriptor_bytes)
{
    const uint64_t setup = (uint64_t)USB_REQUEST_TYPE_DEVICE_IN |
        ((uint64_t)USB_REQUEST_GET_DESCRIPTOR << 8) |
        ((uint64_t)descriptor_type << 24) |
        ((uint64_t)descriptor_bytes << 48);
    ring[trb_index].parameter = setup;
    ring[trb_index].status = 8;
    ring[trb_index].control = TRB_CYCLE | TRB_CHAIN | TRB_IDT |
        (TRB_TYPE_SETUP << TRB_TYPE_SHIFT) | TRB_TRT_IN;
    ring[trb_index + 1].parameter = buffer_dma;
    ring[trb_index + 1].status = descriptor_bytes;
    ring[trb_index + 1].control = TRB_CYCLE | TRB_CHAIN | TRB_ISP |
        (TRB_TYPE_DATA << TRB_TYPE_SHIFT) | TRB_DIR_IN;
    ring[trb_index + 2].control = TRB_CYCLE | TRB_IOC |
        (TRB_TYPE_STATUS << TRB_TYPE_SHIFT);
}

int
rpi5_usb_k65_descriptor_batch(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes,
    struct rpi5_usb_xhci_descriptor_batch *output)
{
    if (!output || !valid_layout(layout, allocation, allocation_bytes, 91)) {
        return -1;
    }
    static const uint8_t types[RPI5_USB_K65_DESCRIPTOR_TRANSFERS] = {
        RPI5_USB_DESCRIPTOR_DEVICE, RPI5_USB_DESCRIPTOR_DEVICE,
        RPI5_USB_DESCRIPTOR_CONFIGURATION,
        RPI5_USB_DESCRIPTOR_CONFIGURATION,
    };
    static const uint16_t sizes[RPI5_USB_K65_DESCRIPTOR_TRANSFERS] = {
        8, 18, 9, 91,
    };
    static const uint16_t offsets[RPI5_USB_K65_DESCRIPTOR_TRANSFERS] = {
        0x000, 0x040, 0x080, 0x100,
    };
    volatile uint8_t *base = allocation;
    volatile struct xhci_trb *ring =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->endpoint0_ring.offset);
    volatile uint8_t *buffer = base + layout->control_buffer.offset;
    for (uint32_t index = 0; index < EP0_RING_BYTES; index++) {
        ((volatile uint8_t *)ring)[index] = 0;
        buffer[index] = 0;
    }
    struct rpi5_usb_xhci_descriptor_batch result = {
        .version = 1,
        .transfer_count = RPI5_USB_K65_DESCRIPTOR_TRANSFERS,
        .trb_count = RPI5_USB_K65_DESCRIPTOR_TRANSFERS *
            RPI5_USB_XHCI_CONTROL_TRBS,
        .link_control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
            (TRB_TYPE_LINK << TRB_TYPE_SHIFT),
        .ring_dma = layout->endpoint0_ring.dma,
        .link_trb_dma = layout->endpoint0_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
    };
    for (uint32_t index = 0; index < result.transfer_count; index++) {
        const uint32_t trb = index * RPI5_USB_XHCI_CONTROL_TRBS;
        const uint64_t buffer_dma = layout->control_buffer.dma + offsets[index];
        write_descriptor(ring, trb, buffer_dma, types[index], sizes[index]);
        result.transfer[index] =
            (struct rpi5_usb_xhci_descriptor_transfer){
                .descriptor_type = types[index],
                .descriptor_bytes = sizes[index],
                .buffer_offset = offsets[index],
                .trb_index = trb,
                .buffer_dma = buffer_dma,
                .status_trb_dma = layout->endpoint0_ring.dma +
                    (trb + 2) * TRB_BYTES,
            };
    }
    ring[RING_TRBS - 1].parameter = layout->endpoint0_ring.dma;
    ring[RING_TRBS - 1].control = result.link_control;
    *output = result;
    return 0;
}

int
rpi5_usb_k65_descriptor_complete(
    const struct rpi5_usb_xhci_descriptor_batch *batch,
    uint32_t transfer_index, const struct rpi5_usb_xhci_transfer_event *event,
    uint8_t expected_cycle, uint8_t expected_slot)
{
    if (!batch || !event || batch->version != 1 ||
        batch->transfer_count != RPI5_USB_K65_DESCRIPTOR_TRANSFERS ||
        batch->trb_count != 12 || transfer_index >= batch->transfer_count ||
        expected_cycle > 1 || !expected_slot || expected_slot > 64 ||
        event->parameter != batch->transfer[transfer_index].status_trb_dma ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_TRANSFER_EVENT ||
        ((event->control >> ENDPOINT_ID_SHIFT) & ENDPOINT_ID_MASK) != 1 ||
        (event->control >> SLOT_ID_SHIFT) != expected_slot ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS ||
        (event->status & UINT32_C(0xffffff))) {
        return -1;
    }
    return 0;
}
