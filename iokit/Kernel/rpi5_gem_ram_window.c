/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_ram_window.h"
static int preferred(const struct rpi5_pcie_fdt *f)
{
    if (!f || f->dma_count!=3 || f->rp1_dma_count!=3) return 0;
    const struct rpi5_pcie_window *p=&f->dma[1];
    const struct rpi5_rp1_dma_window *r=&f->rp1_dma[0];
    return p->space==UINT32_C(0x43000000) && p->cpu_base==0 &&
        p->pci_base==UINT64_C(0x1000000000) && p->size==UINT64_C(0x1000000000) &&
        r->space==p->space && r->pci_base==p->pci_base &&
        r->rp1_base==p->pci_base && r->size==p->size;
}
static int equal(const struct rpi5_pcie_window_plan *a,
    const struct rpi5_pcie_window_plan *b)
{
    for (unsigned i=0;i<3;i++) {
        const struct rpi5_pcie_inbound_encoding *x=&a->inbound[i],*y=&b->inbound[i];
        if (x->cpu_base!=y->cpu_base || x->pci_base!=y->pci_base || x->size!=y->size ||
            x->bar_lo!=y->bar_lo || x->bar_hi!=y->bar_hi ||
            x->remap_lo!=y->remap_lo || x->remap_hi!=y->remap_hi) return 0;
    }
    for (unsigned i=0;i<2;i++) {
        const struct rpi5_pcie_outbound_encoding *x=&a->outbound[i],*y=&b->outbound[i];
        if (x->cpu_base!=y->cpu_base || x->declared_end!=y->declared_end ||
            x->decode_end!=y->decode_end || x->pci_base!=y->pci_base || x->size!=y->size ||
            x->pci_lo!=y->pci_lo || x->pci_hi!=y->pci_hi || x->base_limit!=y->base_limit ||
            x->base_hi!=y->base_hi || x->limit_hi!=y->limit_hi || x->padding_bytes!=y->padding_bytes) return 0;
    }
    return 1;
}
int rpi5_gem_ram_window_plan(const struct rpi5_pcie_fdt *f,
    struct rpi5_pcie_window_plan *out)
{
    if (!out || !preferred(f)) return -1;
    struct rpi5_pcie_window_plan result;
    if (rpi5_pcie_windows_plan(f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&result)) return -2;
    /* BCM2712 size encoding 21 denotes the exact declared 64GiB viewport.
     * No caller-supplied size code or MIP/device alias can select this route. */
    if (result.inbound[1].bar_lo!=21 || result.inbound[1].bar_hi!=16 ||
        result.inbound[1].remap_lo!=1 || result.inbound[1].remap_hi) return -3;
    result.inbound[0].bar_lo&=~UINT32_C(31);
    result.inbound[2].bar_lo&=~UINT32_C(31);
    *out=result;return 0;
}
int rpi5_gem_ram_window_match(const struct rpi5_pcie_fdt *f,
    const struct rpi5_pcie_window_plan *live)
{
    if (!live) return -1;
    struct rpi5_pcie_window_plan expected;
    int rc=rpi5_gem_ram_window_plan(f,&expected);
    return rc ? rc : equal(live,&expected) ? 0 : -4;
}
