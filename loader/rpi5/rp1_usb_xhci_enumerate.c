/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_enumerate.h"

#include "rp1_usb_xhci_lifecycle.h"

#define POLL_US UINT32_C(100)
#define RUN_POLLS UINT32_C(200)
#define EVENT_POLLS UINT32_C(10000)
#define HALT_POLLS UINT32_C(200)
#define MAX_PORT_STATUS_EVENTS 8u

#define OP_PAGESIZE UINT32_C(0x08)
#define OP_CRCR UINT32_C(0x18)
#define OP_DCBAAP UINT32_C(0x30)
#define OP_CONFIG UINT32_C(0x38)
#define RT_IMAN0 UINT32_C(0x20)
#define RT_IMOD0 UINT32_C(0x24)
#define RT_ERSTSZ0 UINT32_C(0x28)
#define RT_ERSTBA0 UINT32_C(0x30)
#define RT_ERDP0 UINT32_C(0x38)
#define ERDP_EVENT_HANDLER_BUSY UINT64_C(8)

#define TRB_CYCLE UINT32_C(1)
#define TRB_TYPE_SHIFT 10u
#define TRB_TYPE_MASK UINT32_C(0x3f)
#define TRB_TYPE_COMMAND_COMPLETION 33u
#define TRB_TYPE_PORT_STATUS_CHANGE 34u
#define TRB_TYPE_TRANSFER_EVENT 32u
#define COMPLETION_CODE_SUCCESS 1u

struct event_trb {
    volatile uint64_t parameter;
    volatile uint32_t status, control;
};

static int
guard(const struct rpi5_xhci_enumerate_io *io,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    if (io->guard(io->context)) {
        trace->error = error;
        return -1;
    }
    return 0;
}

static int
dma_guard(const struct rpi5_xhci_enumerate_io *io,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    if (guard(io, trace, error) || io->dma_guard(io->context) ||
        guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->dma_checks++;
    return 0;
}

static int
read32(const struct rpi5_xhci_enumerate_io *io, uint32_t offset,
    uint32_t *value, struct rpi5_xhci_enumerate_observation *trace, int error)
{
    if (guard(io, trace, error) || io->read32(io->context, offset, value) ||
        *value == UINT32_MAX || guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->reads++;
    return 0;
}

static int
write32(const struct rpi5_xhci_enumerate_io *io, uint32_t offset,
    uint32_t value, struct rpi5_xhci_enumerate_observation *trace, int error)
{
    if (guard(io, trace, error) || io->write32(io->context, offset, value) ||
        guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->writes++;
    return 0;
}

static int
write64(const struct rpi5_xhci_enumerate_io *io, uint32_t offset,
    uint64_t value, struct rpi5_xhci_enumerate_observation *trace, int error)
{
    return write32(io, offset, (uint32_t)value, trace, error) ||
        write32(io, offset + 4, (uint32_t)(value >> 32), trace, error);
}

static int
delay(const struct rpi5_xhci_enumerate_io *io,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    if (guard(io, trace, error) || io->delay_us(io->context, POLL_US) ||
        guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->delayed_us += POLL_US;
    return 0;
}

static int
poll_status(const struct rpi5_xhci_enumerate_io *io, uint32_t offset,
    uint32_t halted, uint32_t limit, uint32_t *last,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    for (uint32_t index = 0; index < limit; index++) {
        if (read32(io, offset, last, trace, error)) return -1;
        trace->polls++;
        if ((*last & (RPI5_XHCI_USBSTS_FATAL | RPI5_XHCI_USBSTS_CNR))) {
            trace->error = error;
            return -1;
        }
        if ((*last & RPI5_XHCI_USBSTS_HALTED) == halted) return 0;
        if (delay(io, trace, error)) return -1;
    }
    trace->error = error;
    return -1;
}

static int
consume_event(const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_enumerate_io *io, uint32_t runtime,
    struct rpi5_usb_xhci_event_trb *result,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    volatile struct event_trb *events =
        (volatile struct event_trb *)(uintptr_t)layout->event_ring.cpu;
    for (uint32_t poll = 0; poll < EVENT_POLLS; poll++) {
        if (guard(io, trace, error)) return -1;
        __asm__ volatile("" ::: "memory");
        volatile struct event_trb *event = &events[trace->event_index];
        const uint32_t control = event->control;
        trace->polls++;
        if (control & TRB_CYCLE) {
            result->parameter = event->parameter;
            result->status = event->status;
            result->control = control;
            __asm__ volatile("" ::: "memory");
            trace->event_type =
                (control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK;
            trace->completion_code = result->status >> 24;
            if (dma_guard(io, trace, error)) return -1;
            trace->event_index++;
            if (write64(io, runtime + RT_ERDP0,
                    layout->event_ring.dma +
                        (uint64_t)trace->event_index * RPI5_XHCI_TRB_BYTES |
                        ERDP_EVENT_HANDLER_BUSY,
                    trace, error)) return -1;
            return 0;
        }
        if (delay(io, trace, error)) return -1;
    }
    trace->error = error;
    return -1;
}

static int
next_non_port_event(const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_enumerate_io *io, uint32_t runtime,
    struct rpi5_usb_xhci_event_trb *event,
    struct rpi5_xhci_enumerate_observation *trace, int error)
{
    for (;;) {
        if (consume_event(layout, io, runtime, event, trace, error)) return -1;
        if (trace->event_type != TRB_TYPE_PORT_STATUS_CHANGE) return 0;
        if (trace->completion_code != COMPLETION_CODE_SUCCESS ||
            (event->parameter >> 24) != RPI5_XHCI_K65_ROOT_PORT ||
            (event->parameter & UINT64_C(0xffffff)) ||
            trace->port_status_events == MAX_PORT_STATUS_EVENTS) {
            trace->error = error;
            return -1;
        }
        trace->port_status_events++;
    }
}

static int
valid(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_noop_image *base,
    const struct rpi5_usb_xhci_enable_slot_plan *enable,
    const struct rpi5_usb_xhci_descriptor_batch *batch)
{
    return caps->interface_version == 0x110 &&
        caps->capability_length == 0x20 && caps->max_slots == 64 &&
        caps->max_interrupters == 4 && caps->max_ports == 3 &&
        caps->max_scratchpad_buffers == 64 && caps->address_64 &&
        caps->context_64 && layout->version == 1 &&
        layout->allocation_bytes == RPI5_XHCI_DMA_ALLOCATION_BYTES &&
        layout->scratchpad_count == 64 && base->version == 1 &&
        base->dcbaa_dma == layout->dcbaa.dma &&
        base->command_ring_dma == layout->command_ring.dma &&
        base->event_ring_dma == layout->event_ring.dma &&
        base->erst_dma == layout->erst.dma && base->erst_size == 1 &&
        enable->version == 1 && enable->trb_count == 1 &&
        enable->command_trb_dma == layout->command_ring.dma &&
        enable->link_trb_dma == base->link_trb_dma &&
        batch->version == 1 && batch->transfer_count == 4 &&
        batch->trb_count == 12 && batch->ring_dma ==
            layout->endpoint0_ring.dma;
}

static int
enumerate_k65(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_noop_image *base,
    const struct rpi5_usb_xhci_enable_slot_plan *enable,
    const struct rpi5_usb_xhci_descriptor_batch *batch,
    const struct rpi5_xhci_enumerate_io *io,
    int leave_running,
    struct rpi5_xhci_enumerate_observation *output)
{
    struct rpi5_xhci_enumerate_observation trace = {.version = 1};
    if (!caps || !layout || !base || !enable || !batch || !io || !output ||
        !io->read32 || !io->write32 || !io->delay_us || !io->guard ||
        !io->dma_guard || !io->stage_address ||
        !valid(caps, layout, base, enable, batch)) return -1;
    const uint32_t op = caps->capability_length;
    const uint32_t runtime = caps->runtime_offset;
    const uint32_t doorbell = caps->doorbell_offset;
    if (runtime > RPI5_RP1_USB_WINDOW_SIZE - RT_ERDP0 - 8 ||
        doorbell > RPI5_RP1_USB_WINDOW_SIZE - (64 + 1) * 4) {
        trace.error = -1; *output = trace; return -1;
    }
    trace.operational_base = op;
    trace.runtime_base = runtime;
    trace.doorbell_base = doorbell;

    trace.step = 1;
    if (read32(io, op + OP_PAGESIZE, &trace.page_size, &trace, -2) ||
        read32(io, op, &trace.command_before, &trace, -2) ||
        read32(io, op + 4, &trace.status_before, &trace, -2) ||
        read32(io, runtime + RT_IMAN0, &trace.interrupt_before, &trace, -2) ||
        !(trace.page_size & 1) || (trace.command_before & UINT32_C(0x0f)) ||
        !(trace.status_before & RPI5_XHCI_USBSTS_HALTED) ||
        (trace.status_before & (RPI5_XHCI_USBSTS_FATAL |
            RPI5_XHCI_USBSTS_CNR)) || (trace.interrupt_before & 2)) {
        if (!trace.error) trace.error = -3;
        *output = trace; return -1;
    }

    trace.step = 2;
    if (write64(io, op + OP_DCBAAP, base->dcbaa_dma, &trace, -4) ||
        write64(io, op + OP_CRCR, base->command_ring_dma | 1, &trace, -4) ||
        write32(io, op + OP_CONFIG, 1, &trace, -4) ||
        write32(io, runtime + RT_IMOD0, 0, &trace, -4) ||
        write32(io, runtime + RT_ERSTSZ0, 1, &trace, -4) ||
        write64(io, runtime + RT_ERSTBA0, base->erst_dma, &trace, -4) ||
        write64(io, runtime + RT_ERDP0, base->event_ring_dma, &trace, -4) ||
        dma_guard(io, &trace, -5)) {
        *output = trace; return -1;
    }

    trace.step = 3;
    if (write32(io, op, RPI5_XHCI_USBCMD_RUN_STOP, &trace, -6) ||
        poll_status(io, op + 4, 0, RUN_POLLS, &trace.status_running,
            &trace, -7) || dma_guard(io, &trace, -7)) {
        *output = trace; return -1;
    }

    trace.step = 4;
    const struct rpi5_xhci_port_reset_io port_io = {
        io->read32, io->write32, io->delay_us, io->guard, io->context,
    };
    if (dma_guard(io, &trace, -8) ||
        rpi5_rp1_xhci_reset_k65_port(caps, &port_io, &trace.port) ||
        dma_guard(io, &trace, -8)) {
        trace.error = -8; *output = trace; return -1;
    }

    trace.step = 5;
    if (write32(io, doorbell, 0, &trace, -9)) {
        *output = trace; return -1;
    }
    struct rpi5_usb_xhci_event_trb event;
    if (next_non_port_event(layout, io, runtime, &event, &trace, -10) ||
        trace.event_type != TRB_TYPE_COMMAND_COMPLETION ||
        rpi5_usb_xhci_enable_slot_complete(enable, &event, 1, &trace.slot)) {
        if (!trace.error) trace.error = -10;
        *output = trace; return -1;
    }

    trace.step = 6;
    if (dma_guard(io, &trace, -11) ||
        io->stage_address(io->context, trace.slot, &trace.address) ||
        dma_guard(io, &trace, -11) ||
        write32(io, doorbell, 0, &trace, -11) ||
        next_non_port_event(layout, io, runtime, &event, &trace, -12) ||
        trace.event_type != TRB_TYPE_COMMAND_COMPLETION ||
        rpi5_usb_xhci_address_k65_complete(&trace.address, &event, 1)) {
        if (!trace.error) trace.error = -12;
        *output = trace; return -1;
    }

    trace.step = 7;
    if (dma_guard(io, &trace, -13) ||
        write32(io, doorbell + (uint32_t)trace.slot * 4, 1,
            &trace, -13)) {
        *output = trace; return -1;
    }
    for (uint32_t index = 0; index < batch->transfer_count; index++) {
        if (next_non_port_event(layout, io, runtime, &event, &trace, -14) ||
            trace.event_type != TRB_TYPE_TRANSFER_EVENT) {
            if (!trace.error) trace.error = -14;
            *output = trace; return -1;
        }
        const struct rpi5_usb_xhci_transfer_event transfer_event = {
            event.parameter, event.status, event.control,
        };
        if (rpi5_usb_k65_descriptor_complete(batch, index,
                &transfer_event, 1, trace.slot)) {
            trace.error = -14;
            *output = trace; return -1;
        }
    }

    trace.step = 8;
    if (leave_running) {
        if (dma_guard(io, &trace, -15) ||
            read32(io, op + 4, &trace.status_halted, &trace, -16) ||
            read32(io, op, &trace.command_halted, &trace, -17) ||
            !(trace.command_halted & RPI5_XHCI_USBCMD_RUN_STOP) ||
            (trace.command_halted & UINT32_C(0x0e)) ||
            (trace.status_halted & (RPI5_XHCI_USBSTS_HALTED |
                RPI5_XHCI_USBSTS_FATAL | RPI5_XHCI_USBSTS_CNR))) {
            if (!trace.error) trace.error = -17;
            *output = trace; return -1;
        }
        trace.left_running = 1;
    } else {
        if (dma_guard(io, &trace, -15) ||
            write32(io, op, 0, &trace, -15) ||
            poll_status(io, op + 4, RPI5_XHCI_USBSTS_HALTED, HALT_POLLS,
                &trace.status_halted, &trace, -16) ||
            read32(io, op, &trace.command_halted, &trace, -17) ||
            (trace.command_halted & UINT32_C(0x0f))) {
            if (!trace.error) trace.error = -17;
            *output = trace; return -1;
        }
    }

    trace.step = 9;
    const uint8_t *buffers = (const uint8_t *)(uintptr_t)
        layout->control_buffer.cpu;
    const struct rpi5_usb_xhci_descriptor_transfer *d = batch->transfer;
    for (uint32_t index = 0; index < 8; index++) {
        if (buffers[d[0].buffer_offset + index] !=
            buffers[d[1].buffer_offset + index]) {
            trace.error = -18; *output = trace; return -1;
        }
    }
    for (uint32_t index = 0; index < 9; index++) {
        if (buffers[d[2].buffer_offset + index] !=
            buffers[d[3].buffer_offset + index]) {
            trace.error = -18; *output = trace; return -1;
        }
    }
    if (rpi5_usb_k65_boot_keyboard_identify(
            buffers + d[1].buffer_offset, d[1].descriptor_bytes,
            buffers + d[3].buffer_offset, d[3].descriptor_bytes,
            &trace.keyboard)) {
        trace.error = -19; *output = trace; return -1;
    }
    trace.step = 10;
    *output = trace;
    return 0;
}

int
rpi5_rp1_xhci_enumerate_k65(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_noop_image *base,
    const struct rpi5_usb_xhci_enable_slot_plan *enable,
    const struct rpi5_usb_xhci_descriptor_batch *batch,
    const struct rpi5_xhci_enumerate_io *io,
    struct rpi5_xhci_enumerate_observation *output)
{
    return enumerate_k65(caps, layout, base, enable, batch, io, 0, output);
}

int
rpi5_rp1_xhci_enumerate_k65_live(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_noop_image *base,
    const struct rpi5_usb_xhci_enable_slot_plan *enable,
    const struct rpi5_usb_xhci_descriptor_batch *batch,
    const struct rpi5_xhci_enumerate_io *io,
    struct rpi5_xhci_enumerate_observation *output)
{
    return enumerate_k65(caps, layout, base, enable, batch, io, 1, output);
}
