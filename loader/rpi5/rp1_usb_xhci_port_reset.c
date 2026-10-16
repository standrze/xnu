/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_port_reset.h"

#include "rp1_usb_xhci_lifecycle.h"

#define POLL_US UINT32_C(100)
#define RESET_POLLS UINT32_C(2500)
#define OP_PORTS_BASE UINT32_C(0x400)
#define PORT_STRIDE UINT32_C(0x10)

#define PORTSC_CCS UINT32_C(1 << 0)
#define PORTSC_PED UINT32_C(1 << 1)
#define PORTSC_PR UINT32_C(1 << 4)
#define PORTSC_PLS_MASK UINT32_C(0xf << 5)
#define PORTSC_PP UINT32_C(1 << 9)
#define PORTSC_SPEED_MASK UINT32_C(0xf << 10)
#define PORTSC_LWS UINT32_C(1 << 16)
#define PORTSC_CSC UINT32_C(1 << 17)
#define PORTSC_PEC UINT32_C(1 << 18)
#define PORTSC_WRC UINT32_C(1 << 19)
#define PORTSC_OCC UINT32_C(1 << 20)
#define PORTSC_PRC UINT32_C(1 << 21)
#define PORTSC_PLC UINT32_C(1 << 22)
#define PORTSC_CEC UINT32_C(1 << 23)
#define PORTSC_WPR UINT32_C(1u << 31)
#define PORTSC_WRITE_ZERO (PORTSC_PED | PORTSC_PR | PORTSC_PLS_MASK | \
    PORTSC_LWS | PORTSC_CSC | PORTSC_PEC | PORTSC_WRC | PORTSC_OCC | \
    PORTSC_PRC | PORTSC_PLC | PORTSC_CEC | PORTSC_WPR)
#define PORT_SPEED_HIGH 3u

static int
guard(const struct rpi5_xhci_port_reset_io *io,
    struct rpi5_xhci_port_reset_observation *trace, int error)
{
    if (io->guard(io->context)) {
        trace->error = error;
        return -1;
    }
    return 0;
}

static int
read32(const struct rpi5_xhci_port_reset_io *io, uint32_t offset,
    uint32_t *value, struct rpi5_xhci_port_reset_observation *trace, int error)
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
write32(const struct rpi5_xhci_port_reset_io *io, uint32_t offset,
    uint32_t value, struct rpi5_xhci_port_reset_observation *trace, int error)
{
    if (offset != trace->portsc_offset || guard(io, trace, error) ||
        io->write32(io->context, offset, value) || guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->writes++;
    return 0;
}

static int
delay(const struct rpi5_xhci_port_reset_io *io,
    struct rpi5_xhci_port_reset_observation *trace, int error)
{
    if (guard(io, trace, error) || io->delay_us(io->context, POLL_US) ||
        guard(io, trace, error)) {
        trace->error = error;
        return -1;
    }
    trace->delayed_us += POLL_US;
    return 0;
}

int
rpi5_rp1_xhci_reset_k65_port(const struct rpi5_rp1_xhci_caps *caps,
    const struct rpi5_xhci_port_reset_io *io,
    struct rpi5_xhci_port_reset_observation *output)
{
    struct rpi5_xhci_port_reset_observation trace = {
        .version = 1, .port = RPI5_XHCI_K65_ROOT_PORT,
    };
    if (!caps || !io || !output || !io->read32 || !io->write32 ||
        !io->delay_us || !io->guard || caps->capability_length != 0x20 ||
        caps->interface_version != 0x110 || caps->max_ports < trace.port) {
        return -1;
    }
    trace.portsc_offset = caps->capability_length + OP_PORTS_BASE +
        (trace.port - 1) * PORT_STRIDE;
    if (trace.portsc_offset > RPI5_RP1_USB_WINDOW_SIZE - 4) {
        trace.error = -1;
        *output = trace;
        return -1;
    }

    trace.step = 1;
    if (read32(io, caps->capability_length, &trace.command, &trace, -2) ||
        read32(io, caps->capability_length + 4, &trace.status, &trace, -2) ||
        read32(io, trace.portsc_offset, &trace.before, &trace, -2)) {
        *output = trace;
        return -1;
    }
    if (!(trace.command & RPI5_XHCI_USBCMD_RUN_STOP) ||
        (trace.status & (RPI5_XHCI_USBSTS_HALTED |
            RPI5_XHCI_USBSTS_FATAL | RPI5_XHCI_USBSTS_CNR)) ||
        (trace.before & (PORTSC_CCS | PORTSC_PP)) !=
            (PORTSC_CCS | PORTSC_PP) || (trace.before & PORTSC_PR)) {
        trace.error = -3;
        *output = trace;
        return -1;
    }

    trace.step = 2;
    trace.reset_write = (trace.before & ~PORTSC_WRITE_ZERO) | PORTSC_PR;
    if (write32(io, trace.portsc_offset, trace.reset_write, &trace, -4)) {
        *output = trace;
        return -1;
    }
    for (uint32_t index = 0; index < RESET_POLLS; index++) {
        if (read32(io, trace.portsc_offset, &trace.after, &trace, -5)) {
            *output = trace;
            return -1;
        }
        trace.polls++;
        if (!(trace.after & PORTSC_CCS)) {
            trace.error = -6;
            *output = trace;
            return -1;
        }
        if (!(trace.after & PORTSC_PR) && (trace.after & PORTSC_PRC)) {
            break;
        }
        if (delay(io, &trace, -5)) {
            *output = trace;
            return -1;
        }
    }
    if ((trace.after & (PORTSC_CCS | PORTSC_PED | PORTSC_PP | PORTSC_PR |
            PORTSC_PRC)) != (PORTSC_CCS | PORTSC_PED | PORTSC_PP |
            PORTSC_PRC)) {
        trace.error = -7;
        *output = trace;
        return -1;
    }
    trace.speed = (trace.after & PORTSC_SPEED_MASK) >> 10;
    trace.link_state = (trace.after & PORTSC_PLS_MASK) >> 5;
    if (trace.speed != PORT_SPEED_HIGH || trace.link_state != 0) {
        trace.error = -8;
        *output = trace;
        return -1;
    }

    trace.step = 3;
    trace.ack_write = (trace.after & ~PORTSC_WRITE_ZERO) | PORTSC_PRC;
    if (write32(io, trace.portsc_offset, trace.ack_write, &trace, -9) ||
        read32(io, trace.portsc_offset, &trace.final, &trace, -10)) {
        *output = trace;
        return -1;
    }
    if ((trace.final & (PORTSC_CCS | PORTSC_PED | PORTSC_PP)) !=
            (PORTSC_CCS | PORTSC_PED | PORTSC_PP) ||
        (trace.final & (PORTSC_PR | PORTSC_PRC)) ||
        ((trace.final & PORTSC_SPEED_MASK) >> 10) != PORT_SPEED_HIGH ||
        (trace.final & PORTSC_PLS_MASK)) {
        trace.error = -11;
        *output = trace;
        return -1;
    }
    trace.step = 4;
    *output = trace;
    return 0;
}
