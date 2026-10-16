/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_setup.h"

#define EP0_RING_BYTES UINT32_C(0x1000)
#define TRB_BYTES UINT32_C(16)
#define RING_TRBS (EP0_RING_BYTES / TRB_BYTES)
#define FIRST_SETUP_TRB 12u
#define TRB_CYCLE UINT32_C(1)
#define TRB_TOGGLE_CYCLE UINT32_C(2)
#define TRB_CHAIN UINT32_C(1 << 4)
#define TRB_IOC UINT32_C(1 << 5)
#define TRB_IDT UINT32_C(1 << 6)
#define TRB_DIR_IN UINT32_C(1 << 16)
#define TRB_TYPE_SHIFT 10u
#define TRB_TYPE_SETUP 2u
#define TRB_TYPE_STATUS 4u
#define TRB_TYPE_LINK 6u
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
valid(const struct rpi5_xhci_dma_layout *layout, const void *allocation,
    uint32_t allocation_bytes, uint8_t slot)
{
    const uint64_t cpu = (uint64_t)(uintptr_t)allocation;
    return layout && allocation && slot && slot <= 64 &&
        allocation_bytes == RPI5_XHCI_DMA_ALLOCATION_BYTES &&
        layout->version == 1 && layout->allocation_bytes == allocation_bytes &&
        layout->endpoint0_ring.offset == 0x46000 &&
        layout->endpoint0_ring.bytes == EP0_RING_BYTES &&
        layout->endpoint0_ring.cpu == cpu + 0x46000 &&
        !(layout->endpoint0_ring.dma & (TRB_BYTES - 1));
}

int
rpi5_usb_k65_hid_boot_setup_idle(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    uint8_t idle_duration, struct rpi5_usb_hid_boot_setup_plan *output)
{
    if (!output || idle_duration > 1 ||
        !valid(layout, allocation, allocation_bytes, slot)) {
        return -1;
    }
    const uint64_t requests[RPI5_USB_K65_SETUP_TRANSFERS] = {
        UINT64_C(0x0000000000010900),
        UINT64_C(0x0000000000000b21),
        UINT64_C(0x0000000000000a21) |
            ((uint64_t)idle_duration << 24),
    };
    volatile uint8_t *base = allocation;
    volatile struct xhci_trb *ring =
        (volatile struct xhci_trb *)(uintptr_t)(base +
            layout->endpoint0_ring.offset);
    for (uint32_t index = FIRST_SETUP_TRB;
        index < FIRST_SETUP_TRB + RPI5_USB_K65_SETUP_TRANSFERS * 2;
        index++) {
        ring[index] = (struct xhci_trb){0, 0, 0};
    }
    struct rpi5_usb_hid_boot_setup_plan result = {
        .version = 1,
        .slot = slot,
        .transfer_count = RPI5_USB_K65_SETUP_TRANSFERS,
        .trb_count = RPI5_USB_K65_SETUP_TRANSFERS * 2,
        .first_trb = FIRST_SETUP_TRB,
        .idle_duration = idle_duration,
        .link_control = TRB_CYCLE | TRB_TOGGLE_CYCLE |
            (TRB_TYPE_LINK << TRB_TYPE_SHIFT),
        .ring_dma = layout->endpoint0_ring.dma,
        .link_trb_dma = layout->endpoint0_ring.dma +
            (RING_TRBS - 1) * TRB_BYTES,
    };
    for (uint32_t index = 0; index < result.transfer_count; index++) {
        const uint32_t trb = FIRST_SETUP_TRB + index * 2;
        ring[trb].parameter = requests[index];
        ring[trb].status = 8;
        ring[trb].control = TRB_CYCLE | TRB_CHAIN | TRB_IDT |
            (TRB_TYPE_SETUP << TRB_TYPE_SHIFT);
        ring[trb + 1].control = TRB_CYCLE | TRB_IOC | TRB_DIR_IN |
            (TRB_TYPE_STATUS << TRB_TYPE_SHIFT);
        result.transfer[index] = (struct rpi5_usb_hid_boot_setup_transfer){
            .setup_packet = requests[index],
            .setup_trb_dma = layout->endpoint0_ring.dma + trb * TRB_BYTES,
            .status_trb_dma = layout->endpoint0_ring.dma +
                (trb + 1) * TRB_BYTES,
            .setup_control = ring[trb].control,
            .status_control = ring[trb + 1].control,
            .trb_index = trb,
        };
    }
    ring[RING_TRBS - 1].parameter = layout->endpoint0_ring.dma;
    ring[RING_TRBS - 1].control = result.link_control;
    *output = result;
    return 0;
}

int
rpi5_usb_k65_hid_boot_setup(const struct rpi5_xhci_dma_layout *layout,
    void *allocation, uint32_t allocation_bytes, uint8_t slot,
    struct rpi5_usb_hid_boot_setup_plan *output)
{
    return rpi5_usb_k65_hid_boot_setup_idle(layout, allocation,
        allocation_bytes, slot, 1, output);
}

int
rpi5_usb_k65_hid_boot_setup_complete(
    const struct rpi5_usb_hid_boot_setup_plan *plan, uint32_t transfer_index,
    const struct rpi5_usb_xhci_transfer_event *event, uint8_t expected_cycle)
{
    if (!plan || !event || plan->version != 1 || !plan->slot ||
        plan->slot > 64 || plan->transfer_count !=
            RPI5_USB_K65_SETUP_TRANSFERS || plan->trb_count != 6 ||
        plan->first_trb != FIRST_SETUP_TRB ||
        plan->idle_duration > 1 ||
        transfer_index >= plan->transfer_count || expected_cycle > 1 ||
        event->parameter != plan->transfer[transfer_index].status_trb_dma ||
        (event->control & TRB_CYCLE) != expected_cycle ||
        ((event->control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK) !=
            TRB_TYPE_TRANSFER_EVENT ||
        ((event->control >> ENDPOINT_ID_SHIFT) & ENDPOINT_ID_MASK) != 1 ||
        (event->control >> SLOT_ID_SHIFT) != plan->slot ||
        (event->status >> 24) != COMPLETION_CODE_SUCCESS ||
        (event->status & UINT32_C(0xffffff))) {
        return -1;
    }
    return 0;
}
