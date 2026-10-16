/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_windows.h"

#define PHYS_LIMIT (UINT64_C(1) << 40)
#define MEM32_LIMIT (UINT64_C(1) << 32)
#define MIB UINT64_C(0x100000)
#define BASE_LIMIT_MASK UINT32_C(0xfff0fff0)
#define STATUS UINT32_C(0x4068)
#define CONTROL UINT32_C(0x4064)

static int span(uint64_t base, uint64_t size, uint64_t limit)
{
    return size && base < limit && size <= limit - base;
}
static int overlap(uint64_t a, uint64_t an, uint64_t b, uint64_t bn)
{
    return a < b + bn && b < a + an;
}
static uint32_t inbound_size(uint64_t size)
{
    if (size < 0x1000 || size > (UINT64_C(1) << 36) || (size & (size - 1))) return 0;
    uint32_t exponent = 0;
    for (uint64_t v = size; v > 1; v >>= 1) exponent++;
    return exponent <= 15 ? exponent - 12 + 0x1c : exponent - 15;
}
static void copy_plan(struct rpi5_pcie_window_plan *to, const struct rpi5_pcie_window_plan *from)
{
    /* Explicit field copies keep the freestanding target free of memcpy. */
    for (unsigned i = 0; i < 2; i++) {
        const struct rpi5_pcie_outbound_encoding *s = &from->outbound[i];
        struct rpi5_pcie_outbound_encoding *d = &to->outbound[i];
        d->cpu_base = s->cpu_base; d->declared_end = s->declared_end;
        d->decode_end = s->decode_end; d->pci_base = s->pci_base; d->size = s->size;
        d->pci_lo = s->pci_lo; d->pci_hi = s->pci_hi; d->base_limit = s->base_limit;
        d->base_hi = s->base_hi; d->limit_hi = s->limit_hi; d->padding_bytes = s->padding_bytes;
    }
    for (unsigned i = 0; i < 3; i++) {
        const struct rpi5_pcie_inbound_encoding *s = &from->inbound[i];
        struct rpi5_pcie_inbound_encoding *d = &to->inbound[i];
        d->cpu_base = s->cpu_base; d->pci_base = s->pci_base; d->size = s->size;
        d->bar_lo = s->bar_lo; d->bar_hi = s->bar_hi;
        d->remap_lo = s->remap_lo; d->remap_hi = s->remap_hi;
    }
}

int rpi5_pcie_windows_plan(const struct rpi5_pcie_fdt *fdt,
    enum rpi5_pcie_window_padding padding, struct rpi5_pcie_window_plan *out)
{
    if (!fdt || !out || (padding != RPI5_PCIE_WINDOW_EXACT &&
        padding != RPI5_PCIE_WINDOW_ACK_FOUR_BYTES) ||
        fdt->bridge_regs.start != UINT64_C(0x1000120000) ||
        fdt->bridge_regs.end != UINT64_C(0x1000129310) ||
        fdt->outbound_count != 2 || fdt->dma_count != 3) return RPI5_PCIE_WINDOWS_ARGUMENT;
    struct rpi5_pcie_window_plan result;
    for (unsigned i = 0; i < 2; i++) {
        const struct rpi5_pcie_window *w = &fdt->outbound[i];
        if (w->space != (i ? UINT32_C(0x43000000) : UINT32_C(0x02000000)) ||
            !span(w->cpu_base, w->size, PHYS_LIMIT) ||
            !span(w->pci_base, w->size, i ? PHYS_LIMIT : MEM32_LIMIT) ||
            ((w->cpu_base | w->pci_base) & (MIB - 1))) return RPI5_PCIE_WINDOWS_ARGUMENT;
        uint64_t end = w->cpu_base + w->size;
        uint64_t decode_end = ((end - 1) | (MIB - 1)) + 1;
        uint64_t excess = decode_end - end;
        if (excess && !(padding == RPI5_PCIE_WINDOW_ACK_FOUR_BYTES && !i && excess == 4 &&
            w->pci_base == 0 && w->cpu_base == UINT64_C(0x1f00000000) &&
            w->size == UINT64_C(0xfffffffc))) return RPI5_PCIE_WINDOWS_ARGUMENT;
        if (!span(w->pci_base, decode_end - w->cpu_base, i ? PHYS_LIMIT : MEM32_LIMIT))
            return RPI5_PCIE_WINDOWS_ARGUMENT;
        struct rpi5_pcie_outbound_encoding *o = &result.outbound[i];
        uint64_t base_mb = w->cpu_base >> 20, limit_mb = (decode_end - 1) >> 20;
        o->cpu_base = w->cpu_base; o->declared_end = end; o->decode_end = decode_end;
        o->pci_base = w->pci_base; o->size = w->size; o->padding_bytes = (uint32_t)excess;
        o->pci_lo = (uint32_t)w->pci_base; o->pci_hi = (uint32_t)(w->pci_base >> 32);
        o->base_limit = ((uint32_t)base_mb & 0xfff) << 4 |
            ((uint32_t)limit_mb & 0xfff) << 20;
        o->base_hi = (uint32_t)(base_mb >> 12); o->limit_hi = (uint32_t)(limit_mb >> 12);
    }
    const struct rpi5_pcie_outbound_encoding *a = &result.outbound[0], *b = &result.outbound[1];
    /* Prefetch/type flags are not independent hardware memory address spaces. */
    if (overlap(a->cpu_base, a->decode_end - a->cpu_base, b->cpu_base, b->decode_end - b->cpu_base) ||
        overlap(a->pci_base, a->decode_end - a->cpu_base, b->pci_base, b->decode_end - b->cpu_base))
        return RPI5_PCIE_WINDOWS_ARGUMENT;
    for (unsigned i = 0; i < 3; i++) {
        const struct rpi5_pcie_window *w = &fdt->dma[i];
        uint32_t expected = i == 0 ? UINT32_C(0x02000000) :
            (i == 1 ? UINT32_C(0x43000000) : UINT32_C(0x03000000));
        uint32_t encoded = inbound_size(w->size);
        if (w->space != expected || !encoded ||
            !span(w->pci_base, w->size, i ? PHYS_LIMIT : MEM32_LIMIT) ||
            !span(w->cpu_base, w->size, PHYS_LIMIT) ||
            (w->pci_base & (w->size - 1)) || (w->cpu_base & 0xfff))
            return RPI5_PCIE_WINDOWS_ARGUMENT;
        for (unsigned j = 0; j < i; j++) {
            const struct rpi5_pcie_window *v = &fdt->dma[j];
            if (overlap(w->pci_base, w->size, v->pci_base, v->size) ||
                overlap(w->cpu_base, w->size, v->cpu_base, v->size))
                return RPI5_PCIE_WINDOWS_ARGUMENT;
        }
        struct rpi5_pcie_inbound_encoding *v = &result.inbound[i];
        v->cpu_base = w->cpu_base; v->pci_base = w->pci_base; v->size = w->size;
        v->bar_lo = ((uint32_t)w->pci_base & ~UINT32_C(0x1f)) | encoded;
        v->bar_hi = (uint32_t)(w->pci_base >> 32);
        v->remap_lo = ((uint32_t)w->cpu_base & ~UINT32_C(0xfff)) | 1;
        v->remap_hi = (uint32_t)(w->cpu_base >> 32);
    }
    /* The third row is the separate MIP target alias, not installed RAM. */
    if (fdt->dma[2].pci_base != fdt->mip_target.start ||
        !span(fdt->mip_target.start, 0x1000, PHYS_LIMIT) ||
        fdt->mip_target.end != fdt->mip_target.start + 0x1000 ||
        fdt->dma[2].size != 0x1000 || fdt->dma[2].cpu_base != fdt->mip_regs.start ||
        fdt->mip_regs.start != UINT64_C(0x1000130000) ||
        fdt->mip_regs.end != UINT64_C(0x10001300c0)) return RPI5_PCIE_WINDOWS_ARGUMENT;
    copy_plan(out, &result);
    return RPI5_PCIE_WINDOWS_OK;
}

static int valid_io(const struct rpi5_pcie_windows_io *io)
{
    return io && io->physical_base == UINT64_C(0x1000120000) && io->mapped_bytes == 0x9310 &&
        io->check_quiescent && io->read32 && io->write32 && io->order;
}
int rpi5_pcie_windows_init(struct rpi5_pcie_windows *session, const struct rpi5_pcie_fdt *fdt,
    const struct rpi5_pcie_windows_io *io, enum rpi5_pcie_window_padding padding)
{
    if (!session || !valid_io(io)) return RPI5_PCIE_WINDOWS_ARGUMENT;
    if (session->state != RPI5_PCIE_WINDOWS_EMPTY) return RPI5_PCIE_WINDOWS_STATE;
    struct rpi5_pcie_window_plan plan;
    int rc = rpi5_pcie_windows_plan(fdt, padding, &plan);
    if (rc) return rc;
    copy_plan(&session->plan, &plan);
    session->io.context = io->context;
    session->io.physical_base = io->physical_base; session->io.mapped_bytes = io->mapped_bytes;
    session->io.check_quiescent = io->check_quiescent; session->io.read32 = io->read32;
    session->io.write32 = io->write32; session->io.order = io->order;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_WINDOWS_READY;
    return RPI5_PCIE_WINDOWS_OK;
}
static int quarantine(struct rpi5_pcie_windows *s, int rc)
{
    s->state = RPI5_PCIE_WINDOWS_QUARANTINED;
    return rc;
}
static int read_reg(struct rpi5_pcie_windows *s, uint32_t offset, uint32_t *value)
{
    if (s->io.read32(s->io.context, offset, value)) return RPI5_PCIE_WINDOWS_IO;
    s->completed_callbacks++;
    return *value == UINT32_MAX ? RPI5_PCIE_WINDOWS_READBACK : RPI5_PCIE_WINDOWS_OK;
}
static int verify(struct rpi5_pcie_windows *s, uint32_t offset, uint32_t mask, uint32_t expected)
{
    uint32_t value;
    int rc = read_reg(s, offset, &value);
    if (rc) return rc;
    return (value & mask) == expected ? RPI5_PCIE_WINDOWS_OK : RPI5_PCIE_WINDOWS_READBACK;
}
static int write_reg(struct rpi5_pcie_windows *s, uint32_t offset, uint32_t mask, uint32_t value)
{
    uint32_t before = 0;
    int rc;
    if (mask != UINT32_MAX && (rc = read_reg(s, offset, &before))) return rc;
    if (s->io.write32(s->io.context, offset, (before & ~mask) | value)) return RPI5_PCIE_WINDOWS_IO;
    s->completed_callbacks++;
    if (s->io.order(s->io.context)) return RPI5_PCIE_WINDOWS_IO;
    s->completed_callbacks++;
    return verify(s, offset, mask, value);
}
static int guard(struct rpi5_pcie_windows *s, uint32_t *status, uint32_t *control)
{
    if (s->io.check_quiescent(s->io.context)) return RPI5_PCIE_WINDOWS_NOT_QUIESCENT;
    s->completed_callbacks++;
    int rc = read_reg(s, STATUS, status);
    if (rc) return rc;
    if ((*status & 0xf0) != 0x80) return RPI5_PCIE_WINDOWS_NOT_QUIESCENT;
    rc = read_reg(s, CONTROL, control);
    if (rc) return rc;
    /* BCM2712 uses the 7278 PERST# path: bit 2, asserted value zero. */
    return !(*control & 0x5) ?
        RPI5_PCIE_WINDOWS_OK : RPI5_PCIE_WINDOWS_NOT_QUIESCENT;
}

int rpi5_pcie_windows_program(struct rpi5_pcie_windows *s,
    struct rpi5_pcie_windows_observation *out)
{
    if (!s || !out) return RPI5_PCIE_WINDOWS_ARGUMENT;
    if (s->state != RPI5_PCIE_WINDOWS_READY) return RPI5_PCIE_WINDOWS_STATE;
    s->state = RPI5_PCIE_WINDOWS_BUSY;
    if (!valid_io(&s->io)) return quarantine(s, RPI5_PCIE_WINDOWS_ARGUMENT);
    uint32_t status, control;
#define DO(call) do { int rc = (call); if (rc) return quarantine(s, rc); } while (0)
    for (unsigned i = 0; i < 3; i++) {
        const struct rpi5_pcie_inbound_encoding *p = &s->plan.inbound[i];
        DO(guard(s, &status, &control));
        DO(write_reg(s, 0x402c + 8*i, UINT32_MAX, p->bar_lo));
        DO(write_reg(s, 0x4030 + 8*i, UINT32_MAX, p->bar_hi));
        DO(write_reg(s, 0x40ac + 8*i, UINT32_MAX, p->remap_lo));
        DO(write_reg(s, 0x40b0 + 8*i, UINT32_MAX, p->remap_hi));
    }
    for (unsigned i = 0; i < 2; i++) {
        const struct rpi5_pcie_outbound_encoding *p = &s->plan.outbound[i];
        DO(guard(s, &status, &control));
        DO(write_reg(s, 0x400c + 8*i, UINT32_MAX, p->pci_lo));
        DO(write_reg(s, 0x4010 + 8*i, UINT32_MAX, p->pci_hi));
        DO(write_reg(s, 0x4070 + 4*i, BASE_LIMIT_MASK, p->base_limit));
        DO(write_reg(s, 0x4080 + 8*i, 0xff, p->base_hi));
        DO(write_reg(s, 0x4084 + 8*i, 0xff, p->limit_hi));
    }
    /* Verify all target fields again, catching cross-register aliases/drift. */
    for (unsigned i = 0; i < 3; i++) {
        const struct rpi5_pcie_inbound_encoding *p = &s->plan.inbound[i];
        DO(verify(s, 0x402c + 8*i, UINT32_MAX, p->bar_lo));
        DO(verify(s, 0x4030 + 8*i, UINT32_MAX, p->bar_hi));
        DO(verify(s, 0x40ac + 8*i, UINT32_MAX, p->remap_lo));
        DO(verify(s, 0x40b0 + 8*i, UINT32_MAX, p->remap_hi));
    }
    for (unsigned i = 0; i < 2; i++) {
        const struct rpi5_pcie_outbound_encoding *p = &s->plan.outbound[i];
        DO(verify(s, 0x400c + 8*i, UINT32_MAX, p->pci_lo));
        DO(verify(s, 0x4010 + 8*i, UINT32_MAX, p->pci_hi));
        DO(verify(s, 0x4070 + 4*i, BASE_LIMIT_MASK, p->base_limit));
        DO(verify(s, 0x4080 + 8*i, 0xff, p->base_hi));
        DO(verify(s, 0x4084 + 8*i, 0xff, p->limit_hi));
    }
    DO(guard(s, &status, &control));
#undef DO
    out->inbound_programmed = 3; out->outbound_programmed = 2;
    out->padding_bytes = s->plan.outbound[0].padding_bytes;
    out->final_status = status; out->final_control = control;
    out->completed_callbacks = s->completed_callbacks;
    s->state = RPI5_PCIE_WINDOWS_COMPLETE;
    return RPI5_PCIE_WINDOWS_OK;
}
