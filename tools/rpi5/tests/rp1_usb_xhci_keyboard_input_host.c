/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_keyboard_input.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct event_trb { uint64_t parameter; uint32_t status, control; };

struct model {
    uint32_t regs[0x10000 / 4];
    unsigned guards, dma_guards, delays;
};

static int
guard(void *opaque)
{
    ((struct model *)opaque)->guards++;
    return 0;
}

static int
dma_guard(void *opaque)
{
    ((struct model *)opaque)->dma_guards++;
    return 0;
}

static int
read32(void *opaque, uint32_t offset, uint32_t *value)
{
    struct model *model = opaque;
    assert(!(offset & 3) && offset < sizeof model->regs);
    *value = model->regs[offset / 4];
    return 0;
}

static int
allowed_write(uint32_t offset, uint32_t value)
{
    if (offset == 0x20) return value == 0 || value == 1;
    if (offset == 0x498 || offset == 0x49c) return 1;
    if (offset == 0x500) return value == 0;
    if (offset == 0x514) return value == 1 || value == 3;
    return 0;
}

static int
write32(void *opaque, uint32_t offset, uint32_t value)
{
    struct model *model = opaque;
    assert(allowed_write(offset, value));
    if (offset == 0x20 && value == 1) model->regs[0x24 / 4] &= ~1u;
    if (offset == 0x20 && value == 0) model->regs[0x24 / 4] |= 1u;
    model->regs[offset / 4] = value;
    return 0;
}

static int
delay_us(void *opaque, uint32_t us)
{
    struct model *model = opaque;
    assert(us == 100);
    model->delays++;
    return 0;
}

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
    result.runtime_offset = 0x460;
    result.doorbell_offset = 0x500;
    return result;
}

static struct rpi5_usb_boot_keyboard_identity
identity(void)
{
    return (struct rpi5_usb_boot_keyboard_identity){
        .vendor = RPI5_USB_K65_VENDOR,
        .product = RPI5_USB_K65_PRODUCT,
        .report_descriptor_bytes = 154,
        .endpoint_max_packet = 16,
        .configuration = 1,
        .interface = 0,
        .alternate = 0,
        .endpoint = 0x81,
        .interval = 4,
    };
}

int
main(void)
{
    static _Alignas(0x4000) uint8_t allocation[0x50000];
    memset(allocation, 0xa5, sizeof allocation);
    struct rpi5_rp1_xhci_caps capability = caps();
    struct rpi5_xhci_dma_layout layout;
    struct rpi5_xhci_noop_image base;
    struct rpi5_usb_xhci_enable_slot_plan enable;
    struct rpi5_usb_xhci_descriptor_batch descriptors;
    struct rpi5_usb_xhci_address_device_plan address;
    assert(!rpi5_rp1_xhci_dma_layout(&capability, (uint64_t)allocation,
        UINT64_C(0x1100000000), sizeof allocation, &layout));
    assert(!rpi5_rp1_xhci_noop_image(&capability, &layout, allocation,
        sizeof allocation, &base));
    assert(!rpi5_usb_xhci_enable_slot_plan(&layout, allocation,
        sizeof allocation, &enable));
    assert(!rpi5_usb_k65_descriptor_batch(&layout, allocation,
        sizeof allocation, &descriptors));
    assert(!rpi5_usb_xhci_address_k65_plan(&layout, allocation,
        sizeof allocation, 5, &address));
    uint32_t *device = (uint32_t *)(allocation + 0x44000);
    device[0] = UINT32_C(0x08300000);
    device[1] = UINT32_C(0x00020000);
    device[3] = UINT32_C(0x10000001);
    const struct rpi5_usb_boot_keyboard_identity keyboard = identity();
    struct rpi5_usb_xhci_keyboard_endpoint_plan endpoint;
    struct rpi5_usb_hid_boot_setup_plan setup;
    struct rpi5_usb_xhci_keyboard_interrupt_plan interrupt;
    assert(!rpi5_usb_xhci_configure_k65_keyboard(&layout, allocation,
        sizeof allocation, &address, &keyboard, &endpoint));
    assert(!rpi5_usb_k65_hid_boot_setup(&layout, allocation,
        sizeof allocation, 5, &setup));
    assert(!rpi5_usb_xhci_k65_interrupt_plan(&layout, allocation,
        sizeof allocation, &endpoint, &interrupt));

    struct event_trb *events =
        (struct event_trb *)(uintptr_t)layout.event_ring.cpu;
    for (unsigned index = 0; index < 3; index++) {
        events[7 + index] = (struct event_trb){
            setup.transfer[index].status_trb_dma, UINT32_C(1) << 24,
            UINT32_C(1) | (UINT32_C(32) << 10) |
                (UINT32_C(1) << 16) | (UINT32_C(5) << 24)};
    }
    events[10] = (struct event_trb){endpoint.command_trb_dma,
        UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(33) << 10) | (UINT32_C(5) << 24)};
    events[11] = (struct event_trb){interrupt.normal_trb_dma,
        UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(32) << 10) |
            (UINT32_C(3) << 16) | (UINT32_C(5) << 24)};
    uint8_t *report = allocation + layout.keyboard_buffer.offset;
    report[2] = 0x04;

    const struct rpi5_xhci_enumerate_observation enumeration = {
        .version = 1,
        .step = 10,
        .event_index = 7,
        .slot = 5,
        .command_halted = 1,
        .status_halted = 0,
        .left_running = 1,
    };
    struct model model = {0};
    model.regs[0x20 / 4] = 1;
    const struct rpi5_xhci_keyboard_input_io io = {
        &model, read32, write32, delay_us, guard, dma_guard,
    };
    struct rpi5_xhci_keyboard_input_observation out;
    assert(!rpi5_rp1_xhci_k65_keyboard_input(&capability, &layout,
        &enumeration, &endpoint, &setup, &interrupt, &io, &out));
    assert(out.version == 1 && out.step == 7 && out.error == 0 &&
        out.slot == 5 && out.endpoint_id == 3 && out.event_index == 12 &&
        out.command_before == 1 && out.status_before == 0 &&
        out.status_running == 0 && out.status_halted == 1 &&
        out.command_halted == 0 && out.report[2] == 0x04 &&
        out.transfer_index == 3 &&
        out.event_parameter == interrupt.normal_trb_dma &&
        out.event_status == (UINT32_C(1) << 24) &&
        out.event_control == (UINT32_C(1) | (UINT32_C(32) << 10) |
            (UINT32_C(3) << 16) | (UINT32_C(5) << 24)) &&
        out.output_count == 1 && out.output[0] == 'a' &&
        model.regs[0x20 / 4] == 0 && model.regs[0x514 / 4] == 3 &&
        model.dma_guards == out.dma_checks);

    report[2] = 1;
    model.regs[0x20 / 4] = 1;
    model.regs[0x24 / 4] = 0;
    for (unsigned index = 7; index <= 11; index++) events[index].control |= 1;
    assert(rpi5_rp1_xhci_k65_keyboard_input(&capability, &layout,
        &enumeration, &endpoint, &setup, &interrupt, &io, &out));
    assert(out.step == 6 && out.error == -15 && out.command_halted == 0);
    puts("XHCI_KEYBOARD_INPUT_PASS CONFIGURE=DCI3 SETUP=3 REPORT=8 "
        "DECODE=a IRQ_OFF POLLING HALTED=1");
    return 0;
}
