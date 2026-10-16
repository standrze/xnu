/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_keyboard_input.h"

#include "rp1_usb_xhci_lifecycle.h"

#define POLL_US UINT32_C(100)
#define RUN_POLLS UINT32_C(200)
#define EVENT_POLLS UINT32_C(10000)
#define HALT_POLLS UINT32_C(200)
#define MAX_PORT_STATUS_EVENTS 8u
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
guard(const struct rpi5_xhci_keyboard_input_io *io,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
{
    if (io->guard(io->context)) {
        trace->error = error;
        return -1;
    }
    return 0;
}

static int
dma_guard(const struct rpi5_xhci_keyboard_input_io *io,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
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
read32(const struct rpi5_xhci_keyboard_input_io *io, uint32_t offset,
    uint32_t *value, struct rpi5_xhci_keyboard_input_observation *trace,
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
write32(const struct rpi5_xhci_keyboard_input_io *io, uint32_t offset,
    uint32_t value, struct rpi5_xhci_keyboard_input_observation *trace,
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
write64(const struct rpi5_xhci_keyboard_input_io *io, uint32_t offset,
    uint64_t value, struct rpi5_xhci_keyboard_input_observation *trace,
    int error)
{
    return write32(io, offset, (uint32_t)value, trace, error) ||
        write32(io, offset + 4, (uint32_t)(value >> 32), trace, error);
}

static int
delay(const struct rpi5_xhci_keyboard_input_io *io,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
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
poll_status(const struct rpi5_xhci_keyboard_input_io *io, uint32_t offset,
    uint32_t halted, uint32_t limit, uint32_t *last,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
{
    for (uint32_t index = 0; index < limit; index++) {
        if (read32(io, offset, last, trace, error)) return -1;
        trace->polls++;
        if (*last & (RPI5_XHCI_USBSTS_FATAL | RPI5_XHCI_USBSTS_CNR)) {
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
    const struct rpi5_xhci_keyboard_input_io *io, uint32_t runtime,
    struct rpi5_usb_xhci_event_trb *result,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
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
            trace->event_parameter = result->parameter;
            trace->event_status = result->status;
            trace->event_control = result->control;
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
    const struct rpi5_xhci_keyboard_input_io *io, uint32_t runtime,
    struct rpi5_usb_xhci_event_trb *event,
    struct rpi5_xhci_keyboard_input_observation *trace, int error)
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
    const struct rpi5_xhci_enumerate_observation *enumeration,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    const struct rpi5_usb_hid_boot_setup_plan *setup,
    const struct rpi5_usb_xhci_keyboard_interrupt_plan *interrupt)
{
    return caps->capability_length == 0x20 && caps->max_slots == 64 &&
        caps->runtime_offset < RPI5_RP1_USB_WINDOW_SIZE - RT_ERDP0 - 8 &&
        caps->doorbell_offset <
            RPI5_RP1_USB_WINDOW_SIZE - (64 + 1) * 4 &&
        layout->version == 1 && enumeration->version == 1 &&
        enumeration->step == 10 && !enumeration->error &&
        enumeration->slot && enumeration->slot <= 64 &&
        enumeration->event_index < layout->event_ring.bytes /
            RPI5_XHCI_TRB_BYTES &&
        endpoint->version == 1 && endpoint->slot == enumeration->slot &&
        endpoint->endpoint_id == RPI5_USB_K65_ENDPOINT_ID &&
        setup->version == 1 && setup->slot == enumeration->slot &&
        setup->transfer_count == RPI5_USB_K65_SETUP_TRANSFERS &&
        setup->first_trb == 12 &&
        interrupt->version == 1 && interrupt->slot == enumeration->slot &&
        interrupt->endpoint_id == RPI5_USB_K65_ENDPOINT_ID;
}

int
rpi5_rp1_xhci_k65_keyboard_input(
    const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_dma_layout *layout,
    const struct rpi5_xhci_enumerate_observation *enumeration,
    const struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    const struct rpi5_usb_hid_boot_setup_plan *setup,
    const struct rpi5_usb_xhci_keyboard_interrupt_plan *interrupt,
    const struct rpi5_xhci_keyboard_input_io *io,
    struct rpi5_xhci_keyboard_input_observation *output)
{
    struct rpi5_xhci_keyboard_input_observation trace = {.version = 1};
    if (!caps || !layout || !enumeration || !endpoint || !setup ||
        !interrupt || !io || !output || !io->read32 || !io->write32 ||
        !io->delay_us || !io->guard || !io->dma_guard ||
        !valid(caps, layout, enumeration, endpoint, setup, interrupt)) {
        return -1;
    }
    const uint32_t op = caps->capability_length;
    const uint32_t runtime = caps->runtime_offset;
    const uint32_t doorbell = caps->doorbell_offset;
    trace.event_index = enumeration->event_index;
    trace.slot = enumeration->slot;
    trace.endpoint_id = RPI5_USB_K65_ENDPOINT_ID;

    trace.step = 1;
    uint32_t interrupt_state;
    if (read32(io, op, &trace.command_before, &trace, -2) ||
        read32(io, op + 4, &trace.status_before, &trace, -2) ||
        read32(io, runtime + 0x20, &interrupt_state, &trace, -2) ||
        (trace.status_before & (RPI5_XHCI_USBSTS_FATAL |
            RPI5_XHCI_USBSTS_CNR)) || (interrupt_state & 2)) {
        if (!trace.error) trace.error = -3;
        *output = trace; return -1;
    }
    if (enumeration->left_running ?
            (!(trace.command_before & RPI5_XHCI_USBCMD_RUN_STOP) ||
                (trace.command_before & UINT32_C(0x0e)) ||
                (trace.status_before & RPI5_XHCI_USBSTS_HALTED)) :
            ((trace.command_before & UINT32_C(0x0f)) ||
                !(trace.status_before & RPI5_XHCI_USBSTS_HALTED))) {
        trace.error = -3; *output = trace; return -1;
    }

    trace.step = 2;
    if (dma_guard(io, &trace, -4)) {
        *output = trace; return -1;
    }
    if (enumeration->left_running) {
        trace.status_running = trace.status_before;
    } else if (write32(io, op, RPI5_XHCI_USBCMD_RUN_STOP, &trace, -4) ||
        poll_status(io, op + 4, 0, RUN_POLLS, &trace.status_running,
            &trace, -5)) {
        *output = trace; return -1;
    }

    struct rpi5_usb_xhci_event_trb event;
    trace.step = 3;
    if (write32(io, doorbell + (uint32_t)trace.slot * 4, 1,
            &trace, -6)) {
        *output = trace; return -1;
    }
    for (uint32_t index = 0; index < setup->transfer_count; index++) {
        trace.transfer_index = index;
        if (next_non_port_event(layout, io, runtime, &event, &trace, -7) ||
            trace.event_type != TRB_TYPE_TRANSFER_EVENT) {
            if (!trace.error) trace.error = -7;
            *output = trace; return -1;
        }
        const struct rpi5_usb_xhci_transfer_event transfer = {
            event.parameter, event.status, event.control,
        };
        if (rpi5_usb_k65_hid_boot_setup_complete(setup, index,
                &transfer, 1)) {
            trace.error = -7; *output = trace; return -1;
        }
    }

    trace.step = 4;
    if (write32(io, doorbell, 0, &trace, -8) ||
        next_non_port_event(layout, io, runtime, &event, &trace, -9) ||
        trace.event_type != TRB_TYPE_COMMAND_COMPLETION ||
        rpi5_usb_xhci_configure_k65_complete(endpoint, &event, 1)) {
        if (!trace.error) trace.error = -9;
        *output = trace; return -1;
    }

    trace.step = 5;
    trace.transfer_index = setup->transfer_count;
    if (dma_guard(io, &trace, -10) ||
        write32(io, doorbell + (uint32_t)trace.slot * 4,
            RPI5_USB_K65_ENDPOINT_ID, &trace, -10) ||
        next_non_port_event(layout, io, runtime, &event, &trace, -11) ||
        trace.event_type != TRB_TYPE_TRANSFER_EVENT) {
        if (!trace.error) trace.error = -11;
        *output = trace; return -1;
    }
    const struct rpi5_usb_xhci_transfer_event transfer = {
        event.parameter, event.status, event.control,
    };
    if (rpi5_usb_xhci_k65_interrupt_complete(interrupt, &transfer, 1) ||
        dma_guard(io, &trace, -11)) {
        trace.error = -11; *output = trace; return -1;
    }

    trace.step = 6;
    if (write32(io, op, 0, &trace, -12) ||
        poll_status(io, op + 4, RPI5_XHCI_USBSTS_HALTED, HALT_POLLS,
            &trace.status_halted, &trace, -13) ||
        read32(io, op, &trace.command_halted, &trace, -14) ||
        (trace.command_halted & UINT32_C(0x0f)) ||
        dma_guard(io, &trace, -14)) {
        if (!trace.error) trace.error = -14;
        *output = trace; return -1;
    }

    const volatile uint8_t *report =
        (const volatile uint8_t *)(uintptr_t)layout->keyboard_buffer.cpu;
    for (uint32_t index = 0; index < RPI5_USB_HID_BOOT_REPORT_BYTES; index++) {
        trace.report[index] = report[index];
    }
    struct rpi5_usb_hid_boot_keyboard keyboard = {0};
    size_t count = 0;
    if (rpi5_usb_hid_boot_keyboard_report(&keyboard, trace.report,
            trace.output, sizeof(trace.output), &count)) {
        trace.error = -15; *output = trace; return -1;
    }
    trace.output_count = (uint32_t)count;
    trace.step = 7;
    *output = trace;
    return 0;
}
