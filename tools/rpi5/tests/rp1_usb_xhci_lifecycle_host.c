/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "rp1_usb_xhci_lifecycle.h"

struct model {
    uint32_t command, status;
    uint32_t reads, writes, delays, guard_calls;
    uint32_t halt_after, reset_after, ready_after;
    uint32_t reset_reads, status_reads;
    int reject_write, reject_delay, reject_guard;
};

static int
guard(void *context)
{
    struct model *model = context;
    model->guard_calls++;
    return model->reject_guard && model->guard_calls >= (uint32_t)model->reject_guard;
}

static int
read32(void *context, uint32_t offset, uint32_t *value)
{
    struct model *model = context;
    model->reads++;
    if (offset == 0x20) {
        if ((model->command & RPI5_XHCI_USBCMD_HCRST) &&
            ++model->reset_reads >= model->reset_after) {
            model->command &= ~RPI5_XHCI_USBCMD_HCRST;
        }
        *value = model->command;
        return 0;
    }
    if (offset == 0x24) {
        model->status_reads++;
        if (!(model->command & RPI5_XHCI_USBCMD_RUN_STOP) &&
            model->status_reads >= model->halt_after) {
            model->status |= RPI5_XHCI_USBSTS_HALTED;
        }
        if (!(model->command & RPI5_XHCI_USBCMD_HCRST) &&
            model->reset_reads >= model->reset_after &&
            model->status_reads >= model->ready_after) {
            model->status &= ~RPI5_XHCI_USBSTS_CNR;
        }
        *value = model->status;
        return 0;
    }
    return -1;
}

static int
write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *model = context;
    if (offset != 0x20 || model->reject_write) {
        return -1;
    }
    model->writes++;
    model->command = value;
    if (value & RPI5_XHCI_USBCMD_HCRST) {
        model->status |= RPI5_XHCI_USBSTS_CNR | RPI5_XHCI_USBSTS_HALTED;
    }
    return 0;
}

static int
delay_us(void *context, uint32_t value)
{
    struct model *model = context;
    model->delays += value;
    return model->reject_delay ? -1 : 0;
}

static struct rpi5_xhci_lifecycle_io
operations(struct model *model)
{
    return (struct rpi5_xhci_lifecycle_io){
        model, read32, write32, delay_us, guard,
    };
}

static struct model
running(void)
{
    return (struct model){
        .command = RPI5_XHCI_USBCMD_RUN_STOP,
        .status = 0,
        .halt_after = 3,
        .reset_after = 3,
        .ready_after = 6,
    };
}

int
main(void)
{
    const uint32_t caps[RPI5_RP1_XHCI_CAP_WORDS] = {
        0x01100020, 0x03000440, 0x140000f1, 0x07ff000a,
        0x0240fe6d, 0x00000500, 0x00000460, 0x0000002f,
    };
    struct model model = running();
    struct rpi5_xhci_lifecycle_io io = operations(&model);
    struct rpi5_xhci_lifecycle_observation trace;
    assert(!rpi5_rp1_xhci_halt_reset(caps, &io, &trace));
    assert(trace.step == 5 && trace.error == 0 && trace.writes == 2);
    assert(trace.command_before == RPI5_XHCI_USBCMD_RUN_STOP);
    assert(trace.status_after == RPI5_XHCI_USBSTS_HALTED);
    assert(!(trace.command_after & (RPI5_XHCI_USBCMD_RUN_STOP |
        RPI5_XHCI_USBCMD_HCRST)));
    assert(model.writes == 2 && model.delays == trace.delayed_us);

    model = running();
    model.command = 0;
    model.status = RPI5_XHCI_USBSTS_HALTED;
    io = operations(&model);
    assert(!rpi5_rp1_xhci_halt_reset(caps, &io, &trace));
    assert(trace.writes == 1 && model.writes == 1);

    model = running();
    model.status = RPI5_XHCI_USBSTS_FATAL;
    io = operations(&model);
    assert(rpi5_rp1_xhci_halt_reset(caps, &io, &trace));
    assert(trace.error == -3 && trace.writes == 0);

    model = running();
    model.halt_after = UINT32_MAX;
    io = operations(&model);
    assert(rpi5_rp1_xhci_halt_reset(caps, &io, &trace));
    assert(trace.error == -5 && trace.writes == 1);

    model = running();
    model.reject_guard = 8;
    io = operations(&model);
    assert(rpi5_rp1_xhci_halt_reset(caps, &io, &trace));
    assert(trace.error < 0);

    uint32_t bad[RPI5_RP1_XHCI_CAP_WORDS];
    memcpy(bad, caps, sizeof bad);
    bad[0] = 0;
    model = running();
    io = operations(&model);
    assert(rpi5_rp1_xhci_halt_reset(bad, &io, &trace));
    assert(trace.error == -1 && trace.writes == 0 && model.reads == 0);

    puts("RP1_XHCI_LIFECYCLE_PASS HALT_RESET_ONLY=1 PORT_WRITES=0 DMA=0 IRQ=0");
    return 0;
}
