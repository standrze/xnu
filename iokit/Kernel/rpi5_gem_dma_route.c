/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_dma_route.h"
#define LIMIT (UINT64_C(1) << 40)
static int extent(uint64_t base, uint64_t bytes)
{ return bytes && base < LIMIT && bytes <= LIMIT-base; }
static int contained(uint64_t p, uint64_t n, uint64_t base, uint64_t size)
{ return extent(base,size) && p >= base && n <= size && p-base <= size-n; }
static int overlaps(uint64_t p, uint64_t n, const struct rpi5_range *r)
{ return r->start >= r->end || r->end > LIMIT || (p < r->end && r->start < p+n); }
static int same_plan(const struct rpi5_pcie_window_plan *a,
    const struct rpi5_pcie_window_plan *b)
{
    for (unsigned i=0;i<3;i++) {
        const struct rpi5_pcie_inbound_encoding *x=&a->inbound[i], *y=&b->inbound[i];
        if (x->cpu_base!=y->cpu_base || x->pci_base!=y->pci_base || x->size!=y->size ||
            x->bar_lo!=y->bar_lo || x->bar_hi!=y->bar_hi ||
            x->remap_lo!=y->remap_lo || x->remap_hi!=y->remap_hi) return 0;
    }
    for (unsigned i=0;i<2;i++) {
        const struct rpi5_pcie_outbound_encoding *x=&a->outbound[i], *y=&b->outbound[i];
        if (x->cpu_base!=y->cpu_base || x->pci_base!=y->pci_base || x->size!=y->size ||
            x->declared_end!=y->declared_end || x->decode_end!=y->decode_end ||
            x->pci_lo!=y->pci_lo || x->pci_hi!=y->pci_hi || x->base_limit!=y->base_limit ||
            x->base_hi!=y->base_hi || x->limit_hi!=y->limit_hi ||
            x->padding_bytes!=y->padding_bytes) return 0;
    }
    return 1;
}
int rpi5_gem_dma_route(const struct rpi5_pcie_fdt *f,
    const struct rpi5_pcie_window_plan *live, const struct rpi5_fdt_memory *ram,
    const struct rpi5_reservation_plan *reserved, const struct rpi5_range *initrd,
    uint64_t p, uint64_t n, struct rpi5_gem_dma_route *out)
{
    if (!f || !live || !ram || !reserved || !out || !extent(p,n) || !p ||
        !ram->count || ram->count>8 || reserved->fixed.count>32 || reserved->count>8 ||
        f->rp1_dma_count!=3) return -1;
    struct rpi5_pcie_window_plan expected;
    if (rpi5_pcie_windows_plan(f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&expected) ||
        !same_plan(&expected,live)) return -2;
    /* This exact preferred route is in the pinned Pi5 binding. Other aliases
     * may exist but are not selected, ORed into, or treated as identity DMA. */
    const struct rpi5_pcie_window *w=&f->dma[1];
    const struct rpi5_rp1_dma_window *r=&f->rp1_dma[0];
    if (w->space!=0x43000000 || w->cpu_base!=0 || w->pci_base!=UINT64_C(0x1000000000) ||
        w->size!=UINT64_C(0x1000000000) || r->space!=0x43000000 ||
        r->pci_base!=w->pci_base || r->rp1_base!=UINT64_C(0x1000000000) || r->size!=w->size ||
        !contained(p,n,w->cpu_base,w->size)) return -3;
    uint64_t cursor=p;
    for (unsigned i=0;i<ram->count;i++) {
        if (ram->start[i]>=ram->end[i] || ram->end[i]>LIMIT ||
            (i && ram->start[i]<ram->end[i-1])) return -4;
        if (cursor>=ram->start[i] && cursor<ram->end[i])
            cursor=ram->end[i]<p+n ? ram->end[i] : p+n;
    }
    if (cursor!=p+n) return -4;
    for (size_t i=0;i<reserved->fixed.count;i++)
        if (overlaps(p,n,&reserved->fixed.extent[i])) return -5;
    if (initrd && overlaps(p,n,initrd)) return -5;
    for (unsigned i=0;i<reserved->count;i++) {
        const struct rpi5_dynamic_reservation *d=&reserved->request[i];
        /* No alloc-ranges means unconstrained unresolved ownership: refuse. */
        if (!d->size || !d->window_count || d->window_count>8) return -5;
        for (unsigned j=0;j<d->window_count;j++)
            if (overlaps(p,n,&d->window[j])) return -5;
    }
    uint64_t pci=w->pci_base+(p-w->cpu_base);
    if (!contained(pci,n,r->pci_base,r->size)) return -3;
    struct rpi5_gem_dma_route result={p,pci,r->rp1_base+(pci-r->pci_base),n};
    if (!extent(result.rp1,n)) return -3;
    *out=result;
    return 0;
}
