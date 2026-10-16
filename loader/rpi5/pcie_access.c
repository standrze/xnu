/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_access.h"

int rpi5_pcie_access_init(struct rpi5_pcie_access *s, const struct rpi5_pcie_fdt *fdt,
    const struct rpi5_pcie_access_io *io)
{
    if (!s || !fdt || !io || !io->arm_guard || !io->check_guard || !io->now_us ||
        !io->before_read || !io->read || !io->after_read ||
        fdt->bridge_regs.start != UINT64_C(0x1000120000) ||
        fdt->bridge_regs.end != UINT64_C(0x1000129310) ||
        fdt->bridge_reset_regs.start != UINT64_C(0x1001504318) ||
        fdt->bridge_reset_regs.end != UINT64_C(0x1001504348) || fdt->bridge_reset_id != 44 ||
        fdt->rescal_regs.start != UINT64_C(0x1000119500) ||
        fdt->rescal_regs.end != UINT64_C(0x1000119510)) return RPI5_PCIE_ACCESS_ARGUMENT;
    if (s->state != RPI5_PCIE_ACCESS_EMPTY) return RPI5_PCIE_ACCESS_STATE;
    s->io.context = io->context;
    s->io.arm_guard = io->arm_guard;
    s->io.check_guard = io->check_guard;
    s->io.now_us = io->now_us;
    s->io.before_read = io->before_read;
    s->io.read = io->read;
    s->io.after_read = io->after_read;
    s->registers[0] = (struct rpi5_pcie_access_register){fdt->bridge_reset_regs.start+0x20,4};
    s->registers[1] = (struct rpi5_pcie_access_register){fdt->rescal_regs.start,4};
    s->registers[2] = (struct rpi5_pcie_access_register){fdt->rescal_regs.start+8,4};
    static const uint32_t offsets[] = {
        0x4068,0x4064,0x406c,0x4008,0x043c,0x0188,0x04dc,0x00dc,0x00be,0x00bc,0x4304,0x184c
    };
    for (unsigned i = 0; i < 12; i++) {
        s->registers[i+3].address = fdt->bridge_regs.start+offsets[i];
        s->registers[i+3].width = i >= 7 && i <= 9 ? 2 : 4;
    }
    s->completed_callbacks = 0;
    s->state = RPI5_PCIE_ACCESS_READY;
    return RPI5_PCIE_ACCESS_OK;
}

static int quarantine(struct rpi5_pcie_access *s, int rc)
{
    s->state = RPI5_PCIE_ACCESS_QUARANTINED;
    return rc;
}

int rpi5_pcie_access_capture(struct rpi5_pcie_access *s,
    struct rpi5_pcie_access_observation *out)
{
    if (!s || !out) return RPI5_PCIE_ACCESS_ARGUMENT;
    if (s->state != RPI5_PCIE_ACCESS_READY) return RPI5_PCIE_ACCESS_STATE;
    s->state = RPI5_PCIE_ACCESS_BUSY;
    const struct rpi5_pcie_access_io *io = &s->io;
    struct rpi5_pcie_access_observation result;
    uint64_t start, last, now;
#define STEP(call) do { \
    if ((call)) return quarantine(s,RPI5_PCIE_ACCESS_IO); \
    s->completed_callbacks++; \
} while (0)
#define CLOCK() do { \
    STEP(io->now_us(io->context,&now)); \
    if (now < last) return quarantine(s,RPI5_PCIE_ACCESS_CLOCK); \
    if (now-start > UINT64_C(5000000)) return quarantine(s,RPI5_PCIE_ACCESS_TIMEOUT); \
    last = now; \
} while (0)
    STEP(io->arm_guard(io->context));
    STEP(io->now_us(io->context,&start));
    last = start;
    for (unsigned pass = 0; pass < 2; pass++) for (unsigned i = 0; i < RPI5_PCIE_ACCESS_REGISTERS; i++) {
        const struct rpi5_pcie_access_register *reg = &s->registers[i];
        STEP(io->check_guard(io->context));
        CLOCK();
        STEP(io->before_read(io->context,pass,i,reg->address,reg->width));
        STEP(io->read(io->context,reg->address,reg->width,&result.values[pass][i]));
        if (result.values[pass][i] == UINT32_MAX ||
            (reg->width == 2 && result.values[pass][i] >= UINT16_MAX))
            return quarantine(s,RPI5_PCIE_ACCESS_VALUE);
        STEP(io->after_read(io->context,pass,i,result.values[pass][i]));
        CLOCK();
    }
    STEP(io->check_guard(io->context));
    CLOCK();
    result.elapsed_us = now-start;
    if (!result.elapsed_us) return quarantine(s,RPI5_PCIE_ACCESS_CLOCK);
#undef CLOCK
#undef STEP
    for (unsigned pass = 0; pass < 2; pass++) for (unsigned i = 0; i < RPI5_PCIE_ACCESS_REGISTERS; i++)
        out->values[pass][i] = result.values[pass][i];
    out->elapsed_us = result.elapsed_us;
    s->state = RPI5_PCIE_ACCESS_COMPLETE;
    return RPI5_PCIE_ACCESS_OK;
}
