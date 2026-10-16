/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_keyboard_stream.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct event_trb { uint64_t parameter; uint32_t status, control; };

struct model {
    uint32_t regs[0x10000 / 4];
    uint8_t emitted[64];
    unsigned emitted_count, guards, dma_guards, delays, emit_fail;
};

static int guard(void *opaque)
{ ((struct model *)opaque)->guards++; return 0; }
static int dma_guard(void *opaque)
{ ((struct model *)opaque)->dma_guards++; return 0; }

static int
read32(void *opaque, uint32_t offset, uint32_t *value)
{
    struct model *model = opaque;
    assert(!(offset & 3) && offset < sizeof model->regs);
    *value = model->regs[offset / 4];
    return 0;
}

static int
write32(void *opaque, uint32_t offset, uint32_t value)
{
    struct model *model = opaque;
    assert(offset == 0x498 || offset == 0x49c || offset == 0x500 ||
        offset == 0x514);
    if (offset == 0x500) assert(value == 0);
    if (offset == 0x514) assert(value == 1 || value == 3);
    model->regs[offset / 4] = value;
    return 0;
}

static int
delay_us(void *opaque, uint32_t us)
{
    assert(us == 100);
    ((struct model *)opaque)->delays++;
    return 0;
}

static int
emit(void *opaque, const uint8_t *bytes, uint32_t count)
{
    struct model *model = opaque;
    if (model->emit_fail) return -1;
    assert(count <= sizeof model->emitted - model->emitted_count);
    memcpy(model->emitted + model->emitted_count, bytes, count);
    model->emitted_count += count;
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

static struct event_trb
transfer_event(uint64_t parameter, uint8_t slot, uint8_t endpoint,
    uint8_t cycle)
{
    return (struct event_trb){parameter, UINT32_C(1) << 24,
        cycle | (UINT32_C(32) << 10) |
            ((uint32_t)endpoint << 16) | ((uint32_t)slot << 24)};
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
    struct rpi5_usb_xhci_keyboard_stream_plan stream;
    assert(!rpi5_usb_xhci_configure_k65_keyboard(&layout, allocation,
        sizeof allocation, &address, &keyboard, &endpoint));
    assert(!rpi5_usb_k65_hid_boot_setup_idle(&layout, allocation,
        sizeof allocation, 5, 0, &setup));
    assert(!rpi5_usb_xhci_k65_stream_plan(&layout, allocation,
        sizeof allocation, &endpoint, &stream));

    struct event_trb *events =
        (struct event_trb *)(uintptr_t)layout.event_ring.cpu;
    for (unsigned index = 0; index < 3; index++) {
        events[7 + index] = transfer_event(
            setup.transfer[index].status_trb_dma, 5, 1, 1);
    }
    events[10] = (struct event_trb){endpoint.command_trb_dma,
        UINT32_C(1) << 24,
        UINT32_C(1) | (UINT32_C(33) << 10) | (UINT32_C(5) << 24)};
    const struct rpi5_xhci_enumerate_observation enumeration = {
        .version = 1,
        .step = 10,
        .event_index = 7,
        .slot = 5,
        .left_running = 1,
    };
    struct model model = {0};
    model.regs[0x20 / 4] = 1;
    const struct rpi5_xhci_keyboard_stream_io io = {
        &model, read32, write32, delay_us, guard, dma_guard, emit,
    };
    struct rpi5_xhci_keyboard_stream_state state;
    struct rpi5_xhci_keyboard_stream_observation out;
    assert(!rpi5_rp1_xhci_k65_keyboard_stream_start(&capability, &layout,
        &enumeration, &endpoint, &setup, &stream, &io, &state, &out));
    assert(out.step == 5 && out.error == 0 && out.setup_transfers == 3 &&
        state.active && state.event_index == 11 && state.event_cycle == 1 &&
        state.report_index == 0 && state.report_cycle == 1 &&
        model.regs[0x500 / 4] == 0 && model.regs[0x514 / 4] == 3);
    assert(rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out) == 1);

    uint8_t *reports = allocation + layout.keyboard_buffer.offset;
    reports[2] = 0x04;
    events[11] = transfer_event(stream.ring_dma, 5, 3, 1);
    model.emit_fail = 1;
    assert(rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out) == -1);
    assert(out.error == -5 && state.reports == 0 &&
        state.event_index == 11 && state.report_index == 0 &&
        reports[2] == 0x04 && model.emitted_count == 0);
    model.emit_fail = 0;
    assert(!rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out));
    assert(out.step == 4 && out.output_count == 1 && out.output[0] == 'a' &&
        state.reports == 1 && state.output_bytes == 1 &&
        state.event_index == 12 && state.report_index == 1 &&
        model.emitted_count == 1 && model.emitted[0] == 'a');
    struct event_trb release = transfer_event(stream.ring_dma + 16, 5, 3, 1);
    events[12] = release;
    assert(!rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out));
    assert(out.output_count == 0 && state.reports == 2 &&
        state.report_index == 2 && model.emitted_count == 1);

    state.event_index = 255;
    state.event_cycle = 1;
    state.report_index = 254;
    state.report_cycle = 1;
    events[255] = transfer_event(stream.ring_dma + 254 * 16, 5, 3, 1);
    assert(!rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out));
    assert(state.event_index == 0 && state.event_cycle == 0 &&
        state.report_index == 0 && state.report_cycle == 0);
    struct event_trb *ring =
        (struct event_trb *)(uintptr_t)layout.keyboard_ring.cpu;
    assert((ring[254].control & 1) == 0);
    reports[2] = 0x06;
    events[0] = transfer_event(stream.ring_dma, 5, 3, 0);
    assert(!rpi5_rp1_xhci_k65_keyboard_stream_poll(&capability, &layout,
        &stream, &io, &state, &out));
    assert(state.event_index == 1 && state.event_cycle == 0 &&
        state.report_index == 1 && state.report_cycle == 0 &&
        (ring[0].control & 1) == 1 && model.emitted_count == 2 &&
        model.emitted[1] == 'c');
    assert(model.dma_guards > 0 && model.guards > model.dma_guards);
    puts("XHCI_KEYBOARD_STREAM_PASS IDLE=0 REPORTS=4 BYTES=2 "
        "TRANSFER_WRAP EVENT_WRAP REARM POLLING IRQ_OFF");
    return 0;
}
