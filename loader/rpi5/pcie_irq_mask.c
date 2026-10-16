/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_irq_mask.h"

static const uint32_t banks[3] = {5, 6, 8};
static const uint32_t masks[3] = {UINT32_MAX, UINT32_MAX, UINT32_C(0x7e0)};

static int fail(struct rpi5_pcie_irq_mask *s)
{
    s->state = RPI5_PCIE_IRQ_QUARANTINED;
    return -1;
}
static int dependencies(const struct rpi5_pcie_irq_mask *s)
{
    return s->io.physical_base == UINT64_C(0x107fff9000) && s->io.mapped_bytes == 0x1000 &&
        s->io.check_owner && s->io.read32 && s->io.write32 && s->io.order;
}
static int owner(struct rpi5_pcie_irq_mask *s)
{
    if (!dependencies(s) || s->io.check_owner(s->io.context)) return -1;
    s->callbacks++;
    return dependencies(s) ? 0 : -1;
}
static int read32(struct rpi5_pcie_irq_mask *s, uint32_t offset, uint32_t *out)
{
    if (owner(s)) return -1;
    uint32_t value;
    if (s->io.read32(s->io.context, offset, &value)) return -1;
    s->callbacks++;
    if (owner(s)) return -1;
    *out = value;
    return 0;
}
static int clear_enable(struct rpi5_pcie_irq_mask *s, unsigned index)
{
    if (owner(s) || s->io.write32(s->io.context, 0x180 + 4*banks[index], masks[index])) return -1;
    s->callbacks++;
    if (owner(s) || owner(s) || s->io.order(s->io.context)) return -1;
    s->callbacks++;
    return owner(s);
}
static int snapshot(struct rpi5_pcie_irq_mask *s, uint32_t enabled[3],
    uint32_t pending[3], uint32_t active[3], int masked)
{
    for (unsigned i = 0; i < 3; i++) {
        if (read32(s, 0x100 + 4*banks[i], &enabled[i]) ||
            read32(s, 0x200 + 4*banks[i], &pending[i]) ||
            read32(s, 0x300 + 4*banks[i], &active[i])) return -1;
        if ((active[i] & masks[i]) || (masked && (enabled[i] & masks[i]))) return -1;
    }
    return 0;
}
static int output_disjoint(struct rpi5_pcie_irq_mask *s, struct rpi5_pcie_irq_observation *out)
{
    uintptr_t a = (uintptr_t)s, b = (uintptr_t)out;
    return a <= UINTPTR_MAX-sizeof(*s) && b <= UINTPTR_MAX-sizeof(*out) &&
        (a+sizeof(*s) <= b || b+sizeof(*out) <= a);
}
int rpi5_pcie_irq_init(struct rpi5_pcie_irq_mask *s, const struct rpi5_pcie_fdt *binding,
    const struct rpi5_pcie_irq_io *io)
{
    if (!s || !binding || !io || s->state != RPI5_PCIE_IRQ_EMPTY) return -1;
    struct rpi5_pcie_irq_mask view = {0}; view.io = *io;
    if (!dependencies(&view) || binding->bridge_regs.start != UINT64_C(0x1000120000) ||
        binding->bridge_regs.end != UINT64_C(0x1000129310) || binding->bridge_reset_id != 44 ||
        !binding->gic_phandle || binding->gic_phandle == UINT32_MAX ||
        binding->bridge_intid[0] != 265 || binding->bridge_intid[1] != 266 ||
        binding->mip_intid_base != 160 || binding->mip_intid_count != 64) return -1;
    for (unsigned i = 0; i < 4; i++) if (binding->intx_intid[i] != 261+i) return -1;
    s->io = *io; s->callbacks = 0; s->state = RPI5_PCIE_IRQ_READY;
    return 0;
}
static int run(struct rpi5_pcie_irq_mask *s, struct rpi5_pcie_irq_observation *out, int begin)
{
    if (!s || !out || !output_disjoint(s, out) ||
        s->state != (begin ? RPI5_PCIE_IRQ_READY : RPI5_PCIE_IRQ_MASKED)) return -1;
    s->state = RPI5_PCIE_IRQ_BUSY;
    /* Per-operation counter: repeated fresh checks cannot overflow it. The
     * actual kernel owner enforces its global finite watchdog check budget. */
    s->callbacks = 0;
    struct rpi5_pcie_irq_observation result = {0};
    if (read32(s, 4, &result.typer) || result.typer == UINT32_MAX || (result.typer & 31) < 8)
        return fail(s);
    if (begin) {
        if (snapshot(s, result.enabled_before, result.pending_before, result.active_before, 0)) return fail(s);
        for (unsigned i = 0; i < 3; i++) if (clear_enable(s, i)) return fail(s);
    }
    for (unsigned pass = 0; pass < 2; pass++)
        if (snapshot(s, result.enabled[pass], result.pending[pass], result.active[pass], 1)) return fail(s);
    uint32_t typer;
    if (read32(s, 4, &typer) || typer != result.typer || owner(s)) return fail(s);
    result.callbacks = s->callbacks;
    s->state = RPI5_PCIE_IRQ_MASKED;
    *out = result;
    return 0;
}
int rpi5_pcie_irq_begin(struct rpi5_pcie_irq_mask *s, struct rpi5_pcie_irq_observation *out)
{
    return run(s, out, 1);
}
int rpi5_pcie_irq_check(struct rpi5_pcie_irq_mask *s, struct rpi5_pcie_irq_observation *out)
{
    return run(s, out, 0);
}
