/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_lifecycle.h"

#define RPI5_XHCI_POLL_US UINT32_C(100)
#define RPI5_XHCI_HALT_POLLS UINT32_C(200)
#define RPI5_XHCI_RESET_POLLS UINT32_C(2500)
#define RPI5_XHCI_RESET_SETTLE_US UINT32_C(1000)

static int
checked_guard(const struct rpi5_xhci_lifecycle_io *io,
    struct rpi5_xhci_lifecycle_observation *trace, int error)
{
    if (io->guard(io->context)) {
        trace->error = error;
        return -1;
    }
    return 0;
}

static int
checked_read(const struct rpi5_xhci_lifecycle_io *io, uint32_t offset,
    uint32_t *value, struct rpi5_xhci_lifecycle_observation *trace, int error)
{
    if (checked_guard(io, trace, error) ||
        io->read32(io->context, offset, value) || *value == UINT32_MAX) {
        trace->error = error;
        return -1;
    }
    trace->reads++;
    return checked_guard(io, trace, error);
}

static int
checked_write(const struct rpi5_xhci_lifecycle_io *io, uint32_t offset,
    uint32_t value, struct rpi5_xhci_lifecycle_observation *trace, int error)
{
    if (checked_guard(io, trace, error) ||
        io->write32(io->context, offset, value)) {
        trace->error = error;
        return -1;
    }
    trace->writes++;
    return checked_guard(io, trace, error);
}

static int
checked_delay(const struct rpi5_xhci_lifecycle_io *io, uint32_t us,
    struct rpi5_xhci_lifecycle_observation *trace, int error)
{
    if (checked_guard(io, trace, error) || io->delay_us(io->context, us)) {
        trace->error = error;
        return -1;
    }
    trace->delayed_us += us;
    return checked_guard(io, trace, error);
}

static int
poll_mask(const struct rpi5_xhci_lifecycle_io *io, uint32_t offset,
    uint32_t mask, uint32_t expected, uint32_t limit, uint32_t *last,
    struct rpi5_xhci_lifecycle_observation *trace, int error)
{
    for (uint32_t i = 0; i < limit; i++) {
        if (checked_read(io, offset, last, trace, error)) {
            return -1;
        }
        trace->polls++;
        if ((*last & mask) == expected) {
            return 0;
        }
        if (checked_delay(io, RPI5_XHCI_POLL_US, trace, error)) {
            return -1;
        }
    }
    trace->error = error;
    return -1;
}

int
rpi5_rp1_xhci_halt_reset(
    const uint32_t raw[RPI5_RP1_XHCI_CAP_WORDS],
    const struct rpi5_xhci_lifecycle_io *io,
    struct rpi5_xhci_lifecycle_observation *output)
{
    struct rpi5_xhci_lifecycle_observation trace = {0};
    if (!raw || !io || !output || !io->read32 || !io->write32 ||
        !io->delay_us || !io->guard) {
        return -1;
    }
    struct rpi5_rp1_xhci_caps caps;
    if (rpi5_rp1_xhci_caps_decode(raw, &caps) ||
        caps.capability_length > RPI5_RP1_USB_WINDOW_SIZE - 8) {
        trace.error = -1;
        *output = trace;
        return -1;
    }
    const uint32_t command_offset = caps.capability_length;
    const uint32_t status_offset = command_offset + 4;
    trace.operational_base = command_offset;
    trace.step = 1;
    if (checked_read(io, command_offset, &trace.command_before, &trace, -2) ||
        checked_read(io, status_offset, &trace.status_before, &trace, -2) ||
        (trace.status_before & RPI5_XHCI_USBSTS_FATAL) ||
        (trace.command_before & RPI5_XHCI_USBCMD_HCRST)) {
        if (!trace.error) {
            trace.error = -3;
        }
        *output = trace;
        return -1;
    }

    trace.step = 2;
    trace.halt_command = trace.command_before & ~RPI5_XHCI_USBCMD_RUN_STOP;
    if (!(trace.status_before & RPI5_XHCI_USBSTS_HALTED)) {
        if (checked_write(io, command_offset, trace.halt_command, &trace, -4) ||
            poll_mask(io, status_offset, RPI5_XHCI_USBSTS_HALTED,
                RPI5_XHCI_USBSTS_HALTED, RPI5_XHCI_HALT_POLLS,
                &trace.status_halted, &trace, -5)) {
            *output = trace;
            return -1;
        }
    } else {
        trace.status_halted = trace.status_before;
    }
    if (trace.status_halted & RPI5_XHCI_USBSTS_FATAL) {
        trace.error = -6;
        *output = trace;
        return -1;
    }

    trace.step = 3;
    uint32_t halted_command = 0;
    if (checked_read(io, command_offset, &halted_command, &trace, -7) ||
        (halted_command & (RPI5_XHCI_USBCMD_RUN_STOP | RPI5_XHCI_USBCMD_HCRST))) {
        if (!trace.error) {
            trace.error = -8;
        }
        *output = trace;
        return -1;
    }
    trace.reset_command = halted_command | RPI5_XHCI_USBCMD_HCRST;
    if (checked_write(io, command_offset, trace.reset_command, &trace, -9) ||
        checked_delay(io, RPI5_XHCI_RESET_SETTLE_US, &trace, -10)) {
        *output = trace;
        return -1;
    }

    trace.step = 4;
    if (poll_mask(io, command_offset, RPI5_XHCI_USBCMD_HCRST, 0,
            RPI5_XHCI_RESET_POLLS, &trace.command_after, &trace, -11) ||
        poll_mask(io, status_offset, RPI5_XHCI_USBSTS_CNR, 0,
            RPI5_XHCI_RESET_POLLS, &trace.status_after, &trace, -12)) {
        *output = trace;
        return -1;
    }
    if ((trace.command_after &
            (RPI5_XHCI_USBCMD_RUN_STOP | RPI5_XHCI_USBCMD_HCRST)) ||
        !(trace.status_after & RPI5_XHCI_USBSTS_HALTED) ||
        (trace.status_after &
            (RPI5_XHCI_USBSTS_FATAL | RPI5_XHCI_USBSTS_CNR))) {
        trace.error = -13;
        *output = trace;
        return -1;
    }
    trace.step = 5;
    *output = trace;
    return 0;
}
