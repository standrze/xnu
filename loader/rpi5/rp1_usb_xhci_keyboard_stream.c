/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_keyboard_stream.h"

#include "rp1_usb_xhci_lifecycle.h"

#define POLL_US UINT32_C(100)
#define EVENT_POLLS UINT32_C(10000)
#define MAX_PORT_STATUS_EVENTS UINT32_C(8)
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

struct transfer_trb {
    volatile uint64_t parameter;
    volatile uint32_t status, control;
};

static int
guard(const struct rpi5_xhci_keyboard_stream_io *io,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
{
    if (io->guard(io->context)) {
        trace->error = error;
        return -1;
    }
    return 0;
}

static int
dma_guard(const struct rpi5_xhci_keyboard_stream_io *io,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
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
read32(const struct rpi5_xhci_keyboard_stream_io *io, uint32_t offset,
    uint32_t *value, struct rpi5_xhci_keyboard_stream_observation *trace,
    int error)
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
write32(const struct rpi5_xhci_keyboard_stream_io *io, uint32_t offset,
    uint32_t value, struct rpi5_xhci_keyboard_stream_observation *trace,
    int error)
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
write64(const struct rpi5_xhci_keyboard_stream_io *io, uint32_t offset,
    uint64_t value, struct rpi5_xhci_keyboard_stream_observation *trace,
    int error)
{
    return write32(io, offset, (uint32_t)value, trace, error) ||
        write32(io, offset + 4, (uint32_t)(value >> 32), trace, error);
}

static int
delay(const struct rpi5_xhci_keyboard_stream_io *io,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
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
advance_event(const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_keyboard_stream_io *io, uint32_t runtime,
    struct rpi5_xhci_keyboard_stream_state *state,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
{
    const uint32_t count = layout->event_ring.bytes / RPI5_XHCI_TRB_BYTES;
    state->event_index++;
    if (state->event_index == count) {
        state->event_index = 0;
        state->event_cycle ^= 1;
    }
    return write64(io, runtime + RT_ERDP0,
        layout->event_ring.dma +
            (uint64_t)state->event_index * RPI5_XHCI_TRB_BYTES |
            ERDP_EVENT_HANDLER_BUSY,
        trace, error);
}

static int
consume_event_wait(const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_keyboard_stream_io *io, uint32_t runtime,
    struct rpi5_xhci_keyboard_stream_state *state,
    struct rpi5_usb_xhci_event_trb *result,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
{
    volatile struct event_trb *events =
        (volatile struct event_trb *)(uintptr_t)layout->event_ring.cpu;
    for (uint32_t poll = 0; poll < EVENT_POLLS; poll++) {
        if (guard(io, trace, error)) return -1;
        __asm__ volatile("" ::: "memory");
        volatile struct event_trb *event = &events[state->event_index];
        uint32_t control = event->control;
        trace->polls++;
        if ((control & TRB_CYCLE) == state->event_cycle) {
            result->parameter = event->parameter;
            result->status = event->status;
            result->control = control;
            trace->event_parameter = result->parameter;
            trace->event_status = result->status;
            trace->event_control = result->control;
            trace->event_type =
                (control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK;
            trace->completion_code = result->status >> 24;
            if (dma_guard(io, trace, error) ||
                advance_event(layout, io, runtime, state, trace, error)) {
                return -1;
            }
            return 0;
        }
        if (delay(io, trace, error)) return -1;
    }
    trace->error = error;
    return -1;
}

static int
next_start_event(const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_keyboard_stream_io *io, uint32_t runtime,
    struct rpi5_xhci_keyboard_stream_state *state,
    struct rpi5_usb_xhci_event_trb *event,
    struct rpi5_xhci_keyboard_stream_observation *trace, int error)
{
    for (;;) {
        if (consume_event_wait(layout, io, runtime, state, event, trace,
                error)) return -1;
        if (trace->event_type != TRB_TYPE_PORT_STATUS_CHANGE) return 0;
        if (trace->completion_code != COMPLETION_CODE_SUCCESS ||
            (event->parameter >> 24) != RPI5_XHCI_K65_ROOT_PORT ||
            (event->parameter & UINT64_C(0xffffff)) ||
            state->port_status_events == MAX_PORT_STATUS_EVENTS) {
            trace->error = error;
            return -1;
        }
        state->port_status_events++;
    }
}

static int
valid_start(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_enumerate_observation *enumeration,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    const struct rpi5_usb_hid_boot_setup_plan *setup,
    const struct rpi5_usb_xhci_keyboard_stream_plan *stream)
{
    return caps->capability_length == 0x20 && caps->max_slots == 64 &&
        caps->runtime_offset < RPI5_RP1_USB_WINDOW_SIZE - RT_ERDP0 - 8 &&
        caps->doorbell_offset <
            RPI5_RP1_USB_WINDOW_SIZE - (64 + 1) * 4 &&
        layout->version == 1 && enumeration->version == 1 &&
        enumeration->step == 10 && !enumeration->error &&
        enumeration->left_running && enumeration->slot &&
        enumeration->slot <= 64 &&
        enumeration->event_index <
            layout->event_ring.bytes / RPI5_XHCI_TRB_BYTES &&
        endpoint->version == 1 && endpoint->slot == enumeration->slot &&
        endpoint->endpoint_id == RPI5_USB_K65_ENDPOINT_ID &&
        setup->version == 1 && setup->slot == enumeration->slot &&
        setup->transfer_count == RPI5_USB_K65_SETUP_TRANSFERS &&
        setup->first_trb == 12 && setup->idle_duration == 0 &&
        stream->version == 1 && stream->slot == enumeration->slot &&
        stream->endpoint_id == RPI5_USB_K65_ENDPOINT_ID &&
        stream->report_count == RPI5_USB_K65_STREAM_REPORTS;
}

int
rpi5_rp1_xhci_k65_keyboard_stream_start(
    const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_enumerate_observation *enumeration,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    const struct rpi5_usb_hid_boot_setup_plan *setup,
    const struct rpi5_usb_xhci_keyboard_stream_plan *stream,
    const struct rpi5_xhci_keyboard_stream_io *io,
    struct rpi5_xhci_keyboard_stream_state *output_state,
    struct rpi5_xhci_keyboard_stream_observation *output)
{
    struct rpi5_xhci_keyboard_stream_observation trace = {.version = 1};
    if (!caps || !layout || !enumeration || !endpoint || !setup || !stream ||
        !io || !output_state || !output || !io->read32 || !io->write32 ||
        !io->delay_us || !io->guard || !io->dma_guard || !io->emit ||
        !valid_start(caps, layout, enumeration, endpoint, setup, stream)) {
        return -1;
    }
    struct rpi5_xhci_keyboard_stream_state state = {
        .version = 1,
        .slot = enumeration->slot,
        .endpoint_id = RPI5_USB_K65_ENDPOINT_ID,
        .event_index = enumeration->event_index,
        .event_cycle = 1,
        .report_cycle = 1,
    };
    const uint32_t op = caps->capability_length;
    const uint32_t runtime = caps->runtime_offset;
    const uint32_t doorbell = caps->doorbell_offset;
    trace.step = 1;
    uint32_t command, status, interrupt_state;
    if (read32(io, op, &command, &trace, -2) ||
        read32(io, op + 4, &status, &trace, -2) ||
        read32(io, runtime + 0x20, &interrupt_state, &trace, -2) ||
        !(command & RPI5_XHCI_USBCMD_RUN_STOP) ||
        (command & UINT32_C(0x0e)) ||
        (status & (RPI5_XHCI_USBSTS_HALTED | RPI5_XHCI_USBSTS_FATAL |
            RPI5_XHCI_USBSTS_CNR)) || (interrupt_state & 2)) {
        if (!trace.error) trace.error = -3;
        *output = trace;
        return -1;
    }
    trace.step = 2;
    if (dma_guard(io, &trace, -4) ||
        write32(io, doorbell + state.slot * 4, 1, &trace, -4)) {
        *output = trace;
        return -1;
    }
    struct rpi5_usb_xhci_event_trb event;
    for (uint32_t index = 0; index < setup->transfer_count; index++) {
        if (next_start_event(layout, io, runtime, &state, &event, &trace,
                -5) || trace.event_type != TRB_TYPE_TRANSFER_EVENT) {
            if (!trace.error) trace.error = -5;
            *output = trace;
            return -1;
        }
        const struct rpi5_usb_xhci_transfer_event transfer = {
            event.parameter, event.status, event.control,
        };
        if (rpi5_usb_k65_hid_boot_setup_complete(setup, index, &transfer,
                (uint8_t)(trace.event_control & TRB_CYCLE))) {
            trace.error = -5;
            *output = trace;
            return -1;
        }
        trace.setup_transfers++;
    }
    trace.step = 3;
    if (write32(io, doorbell, 0, &trace, -6) ||
        next_start_event(layout, io, runtime, &state, &event, &trace, -7) ||
        trace.event_type != TRB_TYPE_COMMAND_COMPLETION ||
        rpi5_usb_xhci_configure_k65_complete(endpoint, &event,
            (uint8_t)(trace.event_control & TRB_CYCLE))) {
        if (!trace.error) trace.error = -7;
        *output = trace;
        return -1;
    }
    trace.step = 4;
    if (dma_guard(io, &trace, -8) ||
        write32(io, doorbell + state.slot * 4,
            RPI5_USB_K65_ENDPOINT_ID, &trace, -8)) {
        *output = trace;
        return -1;
    }
    state.active = 1;
    trace.step = 5;
    trace.event_index = state.event_index;
    trace.event_cycle = state.event_cycle;
    trace.report_index = state.report_index;
    trace.report_cycle = state.report_cycle;
    *output_state = state;
    *output = trace;
    return 0;
}

int
rpi5_rp1_xhci_k65_keyboard_stream_poll(
    const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_usb_xhci_keyboard_stream_plan *stream,
    const struct rpi5_xhci_keyboard_stream_io *io,
    struct rpi5_xhci_keyboard_stream_state *state,
    struct rpi5_xhci_keyboard_stream_observation *output)
{
    struct rpi5_xhci_keyboard_stream_observation trace = {.version = 1};
    if (!caps || !layout || !stream || !io || !state || !output ||
        !io->write32 || !io->guard || !io->dma_guard || !io->emit ||
        state->version != 1 || !state->active ||
        state->slot != stream->slot ||
        state->endpoint_id != RPI5_USB_K65_ENDPOINT_ID ||
        state->event_cycle > 1 || state->report_cycle > 1 ||
        state->event_index >= layout->event_ring.bytes /
            RPI5_XHCI_TRB_BYTES ||
        state->report_index >= stream->report_count) {
        return -1;
    }
    const uint32_t runtime = caps->runtime_offset;
    volatile struct event_trb *events =
        (volatile struct event_trb *)(uintptr_t)layout->event_ring.cpu;
    for (uint32_t skipped = 0; skipped <= MAX_PORT_STATUS_EVENTS; skipped++) {
        trace.step = 1;
        if (guard(io, &trace, -2)) {
            *output = trace;
            return -1;
        }
        __asm__ volatile("" ::: "memory");
        volatile struct event_trb *source = &events[state->event_index];
        uint32_t control = source->control;
        trace.polls++;
        if ((control & TRB_CYCLE) != state->event_cycle) {
            trace.event_index = state->event_index;
            trace.event_cycle = state->event_cycle;
            trace.report_index = state->report_index;
            trace.report_cycle = state->report_cycle;
            trace.reports = state->reports;
            trace.output_bytes = state->output_bytes;
            trace.port_status_events = state->port_status_events;
            *output = trace;
            return 1;
        }
        struct rpi5_usb_xhci_event_trb event = {
            source->parameter, source->status, control,
        };
        trace.event_parameter = event.parameter;
        trace.event_status = event.status;
        trace.event_control = event.control;
        trace.event_type = (control >> TRB_TYPE_SHIFT) & TRB_TYPE_MASK;
        trace.completion_code = event.status >> 24;
        uint8_t event_cycle = (uint8_t)state->event_cycle;
        if (trace.event_type == TRB_TYPE_PORT_STATUS_CHANGE) {
            if (trace.completion_code != COMPLETION_CODE_SUCCESS ||
                (event.parameter >> 24) != RPI5_XHCI_K65_ROOT_PORT ||
                (event.parameter & UINT64_C(0xffffff)) ||
                state->port_status_events == MAX_PORT_STATUS_EVENTS ||
                dma_guard(io, &trace, -3) ||
                advance_event(layout, io, runtime, state, &trace, -3)) {
                if (!trace.error) trace.error = -3;
                *output = trace;
                return -1;
            }
            state->port_status_events++;
            continue;
        }
        trace.step = 2;
        const struct rpi5_usb_xhci_transfer_event transfer = {
            event.parameter, event.status, event.control,
        };
        if (trace.event_type != TRB_TYPE_TRANSFER_EVENT ||
            rpi5_usb_xhci_k65_stream_complete(stream, state->report_index,
                &transfer, event_cycle) || dma_guard(io, &trace, -4)) {
            trace.error = -4;
            *output = trace;
            return -1;
        }
        volatile uint8_t *report =
            (volatile uint8_t *)(uintptr_t)layout->keyboard_buffer.cpu +
            state->report_index * RPI5_USB_K65_REPORT_BYTES;
        for (uint32_t index = 0; index < RPI5_USB_K65_REPORT_BYTES; index++) {
            trace.report[index] = report[index];
        }
        struct rpi5_usb_hid_boot_keyboard keyboard = state->keyboard;
        size_t count = 0;
        if (rpi5_usb_hid_boot_keyboard_report(&keyboard, trace.report,
                trace.output, sizeof(trace.output), &count) ||
            (count && io->emit(io->context, trace.output, (uint32_t)count))) {
            trace.error = -5;
            *output = trace;
            return -1;
        }
        trace.output_count = (uint32_t)count;
        trace.step = 3;
        for (uint32_t index = 0; index < RPI5_USB_K65_REPORT_BYTES; index++) {
            report[index] = 0;
        }
        volatile struct transfer_trb *ring =
            (volatile struct transfer_trb *)(uintptr_t)
                layout->keyboard_ring.cpu;
        __asm__ volatile("" ::: "memory");
        ring[state->report_index].control =
            (stream->normal_control & ~TRB_CYCLE) |
            (state->report_cycle ^ 1);
        __asm__ volatile("" ::: "memory");
        if (dma_guard(io, &trace, -6) ||
            advance_event(layout, io, runtime, state, &trace, -6)) {
            if (!trace.error) trace.error = -6;
            *output = trace;
            return -1;
        }
        state->keyboard = keyboard;
        state->reports++;
        state->output_bytes += (uint32_t)count;
        state->report_index++;
        if (state->report_index == stream->report_count) {
            state->report_index = 0;
            state->report_cycle ^= 1;
        }
        trace.step = 4;
        trace.event_index = state->event_index;
        trace.event_cycle = state->event_cycle;
        trace.report_index = state->report_index;
        trace.report_cycle = state->report_cycle;
        trace.reports = state->reports;
        trace.output_bytes = state->output_bytes;
        trace.port_status_events = state->port_status_events;
        *output = trace;
        return 0;
    }
    trace.error = -7;
    *output = trace;
    return -1;
}
