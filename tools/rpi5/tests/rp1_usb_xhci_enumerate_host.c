/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_enumerate.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct event_trb { uint64_t parameter; uint32_t status, control; };

static const uint8_t device_descriptor[18] = {
    18,1,0x00,0x02,0,0,0,64,0x1c,0x1b,0xaf,0x1b,0x12,0x00,1,2,3,1
};
static const uint8_t configuration_descriptor[91] = {
    9,2,91,0,3,1,0,0xa0,250,
    9,4,0,0,1,3,1,1,0,
    9,0x21,0x00,0x01,0,1,0x22,154,0,
    7,5,0x81,3,16,0,4,
    9,4,1,0,2,3,0,0,0,
    9,0x21,0x00,0x01,0,1,0x22,29,0,
    7,5,0x82,3,0,4,4,
    7,5,0x01,3,0,4,4,
    9,4,2,0,1,3,0,0,0,
    9,0x21,0x00,0x01,0,1,0x22,21,0,
    7,5,0x83,3,64,0,4,
};

struct model {
    uint32_t regs[0x10000 / 4];
    unsigned reads, writes, delays, guards, dma_guards, reset_reads;
    int bad_descriptor;
    uint8_t *allocation;
    struct rpi5_xhci_dma_layout *layout;
};

static int guard(void *opaque)
{
    ((struct model *)opaque)->guards++;
    return 0;
}

static int dma_guard(void *opaque)
{
    ((struct model *)opaque)->dma_guards++;
    return 0;
}

static int read32(void *opaque, uint32_t offset, uint32_t *value)
{
    struct model *m = opaque;
    assert(!(offset & 3) && offset < sizeof m->regs);
    m->reads++;
    if (offset == 0x430 && m->writes) {
        if (m->regs[offset / 4] == 0xe11) {
            *value = m->reset_reads++ ? 0x200e03 : 0xe11;
            return 0;
        }
    }
    *value = m->regs[offset / 4];
    return 0;
}

static int allowed_write(uint32_t offset)
{
    switch (offset) {
    case 0x20: case 0x38: case 0x3c: case 0x50: case 0x54: case 0x58:
    case 0x430: case 0x484: case 0x488: case 0x490: case 0x494:
    case 0x498: case 0x49c: case 0x500: case 0x514:
        return 1;
    default: return 0;
    }
}

static int write32(void *opaque, uint32_t offset, uint32_t value)
{
    struct model *m = opaque;
    assert(allowed_write(offset));
    m->writes++;
    if (offset == 0x20 && value == 1) m->regs[0x24 / 4] &= ~1u;
    else if (offset == 0x20 && value == 0) m->regs[0x24 / 4] |= 1u;
    else if (offset == 0x430 && value == 0x200e01) value = 0xe03;
    m->regs[offset / 4] = value;
    return 0;
}

static int delay_us(void *opaque, uint32_t us)
{
    struct model *m = opaque;
    assert(us == 100);
    m->delays++;
    return 0;
}

static int stage_address(void *opaque, uint8_t slot,
    struct rpi5_usb_xhci_address_device_plan *plan)
{
    struct model *m = opaque;
    return rpi5_usb_xhci_address_k65_plan(m->layout, m->allocation,
        RPI5_XHCI_DMA_ALLOCATION_BYTES, slot, plan);
}

static struct rpi5_rp1_xhci_caps make_caps(void)
{
    struct rpi5_rp1_xhci_caps caps = {0};
    caps.interface_version = 0x110;
    caps.capability_length = 0x20;
    caps.max_slots = 64;
    caps.max_interrupters = 4;
    caps.max_ports = 3;
    caps.max_scratchpad_buffers = 64;
    caps.address_64 = 1;
    caps.context_64 = 1;
    caps.runtime_offset = 0x460;
    caps.doorbell_offset = 0x500;
    return caps;
}

static void prepare_events(struct model *m,
    const struct rpi5_usb_xhci_enable_slot_plan *enable,
    const struct rpi5_usb_xhci_descriptor_batch *batch)
{
    struct event_trb *events = (struct event_trb *)(uintptr_t)
        m->layout->event_ring.cpu;
    events[0] = (struct event_trb){UINT64_C(2) << 24,
        UINT32_C(1) << 24, (UINT32_C(34) << 10) | 1};
    events[1] = (struct event_trb){enable->command_trb_dma,
        UINT32_C(1) << 24, (UINT32_C(33) << 10) | (UINT32_C(5) << 24) | 1};
    events[2] = (struct event_trb){enable->command_trb_dma + 16,
        UINT32_C(1) << 24, (UINT32_C(33) << 10) | (UINT32_C(5) << 24) | 1};
    for (unsigned index = 0; index < 4; index++) {
        events[3 + index] = (struct event_trb){
            batch->transfer[index].status_trb_dma, UINT32_C(1) << 24,
            (UINT32_C(32) << 10) | (UINT32_C(1) << 16) |
                (UINT32_C(5) << 24) | 1};
    }
}

static void prepare_descriptors(struct model *m,
    const struct rpi5_usb_xhci_descriptor_batch *batch)
{
    uint8_t *buffer = m->allocation + m->layout->control_buffer.offset;
    memcpy(buffer + batch->transfer[0].buffer_offset, device_descriptor, 8);
    memcpy(buffer + batch->transfer[1].buffer_offset, device_descriptor, 18);
    memcpy(buffer + batch->transfer[2].buffer_offset,
        configuration_descriptor, 9);
    memcpy(buffer + batch->transfer[3].buffer_offset,
        configuration_descriptor, sizeof configuration_descriptor);
    if (m->bad_descriptor) buffer[batch->transfer[3].buffer_offset + 29] = 0x82;
}

static void setup(struct model *m, uint8_t *allocation,
    struct rpi5_xhci_dma_layout *layout, struct rpi5_xhci_noop_image *base,
    struct rpi5_usb_xhci_enable_slot_plan *enable,
    struct rpi5_usb_xhci_descriptor_batch *batch)
{
    memset(m, 0, sizeof *m);
    memset(allocation, 0xa5, RPI5_XHCI_DMA_ALLOCATION_BYTES);
    struct rpi5_rp1_xhci_caps caps = make_caps();
    assert(!rpi5_rp1_xhci_dma_layout(&caps, (uint64_t)allocation,
        UINT64_C(0x1100000000), RPI5_XHCI_DMA_ALLOCATION_BYTES, layout));
    assert(!rpi5_rp1_xhci_noop_image(&caps, layout, allocation,
        RPI5_XHCI_DMA_ALLOCATION_BYTES, base));
    assert(!rpi5_usb_xhci_enable_slot_plan(layout, allocation,
        RPI5_XHCI_DMA_ALLOCATION_BYTES, enable));
    assert(!rpi5_usb_k65_descriptor_batch(layout, allocation,
        RPI5_XHCI_DMA_ALLOCATION_BYTES, batch));
    m->allocation = allocation;
    m->layout = layout;
    m->regs[0x28 / 4] = 1;
    m->regs[0x24 / 4] = 1;
    m->regs[0x430 / 4] = 0xe01;
    prepare_events(m, enable, batch);
    prepare_descriptors(m, batch);
}

int main(void)
{
    static _Alignas(0x4000) uint8_t allocation[RPI5_XHCI_DMA_ALLOCATION_BYTES];
    struct rpi5_rp1_xhci_caps caps = make_caps();
    struct rpi5_xhci_dma_layout layout;
    struct rpi5_xhci_noop_image base;
    struct rpi5_usb_xhci_enable_slot_plan enable;
    struct rpi5_usb_xhci_descriptor_batch batch;
    struct model model;
    setup(&model, allocation, &layout, &base, &enable, &batch);
    struct rpi5_xhci_enumerate_io io = {
        &model, read32, write32, delay_us, guard, dma_guard, stage_address,
    };
    struct rpi5_xhci_enumerate_observation out;
    assert(!rpi5_rp1_xhci_enumerate_k65(&caps, &layout, &base, &enable,
        &batch, &io, &out));
    assert(out.version == 1 && out.step == 10 && out.error == 0 &&
        out.slot == 5 && out.port.step == 4 && out.port.port == 2 &&
        out.port.speed == 3 && out.port.writes == 2 &&
        out.address.command_trb_dma == UINT64_C(0x1100001010) &&
        out.event_index == 7 && out.port_status_events == 1 &&
        out.keyboard.vendor == 0x1b1c && out.keyboard.product == 0x1baf &&
        out.keyboard.interface == 0 && out.keyboard.endpoint == 0x81 &&
        out.keyboard.endpoint_max_packet == 16 && out.keyboard.interval == 4 &&
        out.keyboard.report_descriptor_bytes == 154 &&
        out.command_halted == 0 && out.status_halted == 1 &&
        model.regs[0x20 / 4] == 0 && model.regs[0x430 / 4] == 0xe03 &&
        model.regs[0x514 / 4] == 1 && model.dma_guards == out.dma_checks);

    setup(&model, allocation, &layout, &base, &enable, &batch);
    model.bad_descriptor = 1;
    prepare_descriptors(&model, &batch);
    assert(rpi5_rp1_xhci_enumerate_k65(&caps, &layout, &base, &enable,
        &batch, &io, &out));
    assert(out.step == 9 && out.error == -19 &&
        model.regs[0x20 / 4] == 0);

    setup(&model, allocation, &layout, &base, &enable, &batch);
    assert(!rpi5_rp1_xhci_enumerate_k65_live(&caps, &layout, &base, &enable,
        &batch, &io, &out));
    assert(out.step == 10 && out.error == 0 && out.left_running == 1 &&
        out.command_halted == 1 && !(out.status_halted & 1) &&
        model.regs[0x20 / 4] == 1);
    puts("XHCI_ENUMERATE_PASS PORT=2 SLOT=5 DESCRIPTORS=4 K65=1b1c:1baf "
        "IRQ_OFF POLLING HALTED=1");
    return 0;
}
