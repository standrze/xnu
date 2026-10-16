/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_noop_run.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    uint32_t regs[0x10000 / 4];
    unsigned reads, writes, delays, guards, dma_guards;
    unsigned fail_write, bad_event, port_event;
    struct rpi5_xhci_dma_layout *layout;
    struct rpi5_xhci_noop_image *image;
};

struct event_trb { uint64_t parameter; uint32_t status, control; };

static int
guard(void *context)
{
    struct model *model = context;
    model->guards++;
    return 0;
}

static int
dma_guard(void *context)
{
    struct model *model = context;
    model->dma_guards++;
    return model->dma_guards == 1 && model->bad_event == 2 ? -1 : 0;
}

static int
read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *model = context;
    assert(!(offset & 3) && offset < sizeof(model->regs));
    model->reads++;
    *value = model->regs[offset / 4];
    return 0;
}

static int
write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *model = context;
    assert(!(offset & 3) && offset < sizeof(model->regs));
    model->writes++;
    if (model->fail_write == model->writes) return -1;
    model->regs[offset / 4] = value;
    if (offset == 0x20 && value == 1) model->regs[0x24 / 4] &= ~1u;
    if (offset == 0x20 && value == 0) model->regs[0x24 / 4] |= 1u;
    if (offset == 0x500) {
        assert(value == 0);
        struct event_trb *event = (struct event_trb *)(uintptr_t)
            model->layout->event_ring.cpu;
        if (model->port_event) {
            event[0].parameter = UINT64_C(2) << 24;
            event[0].status = UINT32_C(1) << 24;
            event[0].control = (UINT32_C(34) << 10) | 1;
            event++;
        }
        event->parameter = model->bad_event ?
            model->image->noop_trb_dma + 16 : model->image->noop_trb_dma;
        event->status = UINT32_C(1) << 24;
        event->control = (UINT32_C(33) << 10) | 1;
    }
    return 0;
}

static int
delay_us(void *context, uint32_t us)
{
    struct model *model = context;
    assert(us == 100);
    model->delays++;
    return 0;
}

static struct rpi5_rp1_xhci_caps
make_caps(void)
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

static void
setup(struct model *model, struct rpi5_xhci_dma_layout *layout,
    struct rpi5_xhci_noop_image *image, unsigned char *allocation)
{
    memset(model, 0, sizeof(*model));
    memset(allocation, 0xa5, 0x50000);
    struct rpi5_rp1_xhci_caps caps = make_caps();
    assert(!rpi5_rp1_xhci_dma_layout(&caps, (uint64_t)allocation,
        0x1100000000, 0x50000, layout));
    assert(!rpi5_rp1_xhci_noop_image(&caps, layout, allocation,
        0x50000, image));
    model->layout = layout;
    model->image = image;
    model->regs[0x28 / 4] = 1;
    model->regs[0x24 / 4] = 1;
}

int
main(void)
{
    static _Alignas(0x4000) unsigned char allocation[0x50000];
    struct rpi5_rp1_xhci_caps caps = make_caps();
    struct rpi5_xhci_dma_layout layout;
    struct rpi5_xhci_noop_image image;
    struct model model;
    setup(&model, &layout, &image, allocation);
    struct rpi5_xhci_noop_run_io io = {
        &model, read32, write32, delay_us, guard, dma_guard};
    struct rpi5_xhci_noop_run_observation trace;
    assert(!rpi5_rp1_xhci_run_noop(&caps, &layout, &image, &io, &trace));
    assert(trace.step == 6 && trace.error == 0 && trace.reads == 7 &&
        trace.writes == 16 && trace.polls == 3 && trace.delayed_us == 0 &&
        trace.page_size == 1 && trace.command_before == 0 &&
        trace.status_before == 1 && trace.interrupt_before == 0 &&
        trace.dma_checks == 6 &&
        trace.command_running == 1 && trace.status_running == 0 &&
        trace.event_parameter == image.noop_trb_dma &&
        trace.event_status == (UINT32_C(1) << 24) &&
        trace.event_control == ((UINT32_C(33) << 10) | 1) &&
        trace.completion_code == 1 && trace.event_type == 33 &&
        trace.port_status_events == 0 &&
        trace.command_halted == 0 && trace.status_halted == 1);
    assert(model.regs[0x50 / 4] == (uint32_t)image.dcbaa_dma &&
        model.regs[0x54 / 4] == (uint32_t)(image.dcbaa_dma >> 32) &&
        model.regs[0x38 / 4] == ((uint32_t)image.command_ring_dma | 1) &&
        model.regs[0x3c / 4] == (uint32_t)(image.command_ring_dma >> 32) &&
        model.regs[0x58 / 4] == 1 && model.regs[0x488 / 4] == 1 &&
        model.regs[0x490 / 4] == (uint32_t)image.erst_dma &&
        model.regs[0x498 / 4] == (uint32_t)(image.event_ring_dma + 24) &&
        model.regs[0x480 / 4] == 0 && model.regs[0x20 / 4] == 0);

    setup(&model, &layout, &image, allocation);
    model.port_event = 1;
    memset(&trace, 0, sizeof(trace));
    assert(!rpi5_rp1_xhci_run_noop(&caps, &layout, &image, &io, &trace));
    assert(trace.step == 6 && trace.error == 0 && trace.writes == 18 &&
        trace.dma_checks == 7 && trace.port_status_events == 1 &&
        trace.event_type == 33 &&
        trace.event_parameter == image.noop_trb_dma &&
        model.regs[0x498 / 4] ==
            (uint32_t)(image.event_ring_dma + 2 * RPI5_XHCI_TRB_BYTES + 8));

    setup(&model, &layout, &image, allocation);
    model.bad_event = 1;
    memset(&trace, 0, sizeof(trace));
    assert(rpi5_rp1_xhci_run_noop(&caps, &layout, &image, &io, &trace));
    assert(trace.step == 4 && trace.error == -10 && model.regs[0x20 / 4] == 1);

    setup(&model, &layout, &image, allocation);
    model.bad_event = 2;
    memset(&trace, 0, sizeof(trace));
    assert(rpi5_rp1_xhci_run_noop(&caps, &layout, &image, &io, &trace));
    assert(trace.step == 2 && trace.error == -5 && model.writes == 11 &&
        model.regs[0x20 / 4] == 0);

    unsigned write_faults = 0;
    for (unsigned write = 1; write <= 16; write++) {
        setup(&model, &layout, &image, allocation);
        model.fail_write = write;
        memset(&trace, 0, sizeof(trace));
        assert(rpi5_rp1_xhci_run_noop(&caps, &layout, &image, &io, &trace));
        assert(trace.error != 0);
        write_faults++;
    }
    printf("XHCI_NOOP_RUN_PASS writes=16 write_faults=%u IRQ_OFF PORTS_UNTOUCHED\n",
        write_faults);
    return 0;
}
