/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_port_reset.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct fixture {
    uint32_t port_reads, writes, delays, guards;
    uint32_t write_offset[2], write_value[2];
    int disconnected, stuck, fail_guard;
};

static int
read32(void *opaque, uint32_t offset, uint32_t *value)
{
    struct fixture *f = opaque;
    if (offset == 0x20) *value = 1;
    else if (offset == 0x24) *value = 0;
    else if (offset == 0x430) {
        f->port_reads++;
        if (f->disconnected) *value = 0xe00;
        else if (f->writes == 0) *value = 0xe01;
        else if (f->writes == 1 && (f->stuck || f->port_reads == 2))
            *value = 0xe11;
        else if (f->writes == 1) *value = 0x200e03;
        else *value = 0xe03;
    } else return -1;
    return 0;
}

static int
write32(void *opaque, uint32_t offset, uint32_t value)
{
    struct fixture *f = opaque;
    if (f->writes >= 2 || offset != 0x430) return -1;
    f->write_offset[f->writes] = offset;
    f->write_value[f->writes++] = value;
    return 0;
}

static int delay_us(void *opaque, uint32_t us)
{
    struct fixture *f = opaque;
    if (us != 100) return -1;
    f->delays++;
    return 0;
}

static int guard(void *opaque)
{
    struct fixture *f = opaque;
    f->guards++;
    return f->fail_guard && f->guards >= 3;
}

static struct rpi5_rp1_xhci_caps
caps(void)
{
    struct rpi5_rp1_xhci_caps result = {0};
    result.interface_version = 0x110;
    result.capability_length = 0x20;
    result.max_ports = 3;
    return result;
}

static struct rpi5_xhci_port_reset_io
callbacks(struct fixture *f)
{
    return (struct rpi5_xhci_port_reset_io){
        read32, write32, delay_us, guard, f,
    };
}

int
main(void)
{
    struct rpi5_rp1_xhci_caps capability = caps();
    struct fixture f = {0};
    struct rpi5_xhci_port_reset_io io = callbacks(&f);
    struct rpi5_xhci_port_reset_observation out;
    assert(!rpi5_rp1_xhci_reset_k65_port(&capability, &io, &out));
    assert(out.version == 1 && out.step == 4 && out.error == 0 &&
        out.port == 2 && out.portsc_offset == 0x430 && out.command == 1 &&
        out.status == 0 && out.before == 0xe01 &&
        out.reset_write == 0xe11 && out.after == 0x200e03 &&
        out.ack_write == 0x200e01 && out.final == 0xe03 &&
        out.speed == 3 && out.link_state == 0 && out.reads == 6 &&
        out.writes == 2 && out.polls == 2 && out.delayed_us == 100 &&
        f.writes == 2 && f.write_offset[0] == 0x430 &&
        f.write_offset[1] == 0x430 && f.write_value[0] == 0xe11 &&
        f.write_value[1] == 0x200e01 && f.delays == 1);

    memset(&f, 0, sizeof f); f.disconnected = 1; io = callbacks(&f);
    assert(rpi5_rp1_xhci_reset_k65_port(&capability, &io, &out));
    assert(out.error == -3 && !f.writes);

    memset(&f, 0, sizeof f); f.fail_guard = 1; io = callbacks(&f);
    assert(rpi5_rp1_xhci_reset_k65_port(&capability, &io, &out));
    assert(out.error == -2 && !f.writes);

    memset(&f, 0, sizeof f); f.stuck = 1; io = callbacks(&f);
    assert(rpi5_rp1_xhci_reset_k65_port(&capability, &io, &out));
    assert(out.error == -7 && f.writes == 1 &&
        f.delays == 2500 && out.polls == 2500);
    puts("XHCI_PORT_RESET_PASS PORT=2 SPEED=HIGH WRITES=2 BOUNDED=1 "
        "NO_OTHER_PORT NO_COMMAND NO_DOORBELL NO_DMA");
    return 0;
}
