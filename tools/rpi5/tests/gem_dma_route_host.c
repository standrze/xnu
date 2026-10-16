/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_dma_route.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void binding(struct rpi5_pcie_fdt *f)
{
    memset(f,0,sizeof *f);
    f->bridge_regs=(struct rpi5_range){0x1000120000,0x1000129310};
    f->mip_regs=(struct rpi5_range){0x1000130000,0x10001300c0};
    f->mip_target=(struct rpi5_range){0xfffffff000,0x10000000000};
    f->outbound_count=2; f->dma_count=3; f->rp1_dma_count=3;
    f->outbound[0]=(struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0xfffffffc};
    f->outbound[1]=(struct rpi5_pcie_window){0x43000000,0x400000000,0x1c00000000,0x300000000};
    f->dma[0]=(struct rpi5_pcie_window){0x02000000,0,0x1f00000000,0x400000};
    f->dma[1]=(struct rpi5_pcie_window){0x43000000,0x1000000000,0,0x1000000000};
    f->dma[2]=(struct rpi5_pcie_window){0x03000000,0xfffffff000,0x1000130000,0x1000};
    f->rp1_dma[0]=(struct rpi5_rp1_dma_window){0x43000000,0x1000000000,0x1000000000,0x1000000000};
    f->rp1_dma[1]=(struct rpi5_rp1_dma_window){0x02000000,0xc040000000,0,0x410000};
    f->rp1_dma[2]=(struct rpi5_rp1_dma_window){0x02000000,0,0x1000000000,0x1000000000};
}
int main(void)
{
    struct rpi5_pcie_fdt f;binding(&f);
    struct rpi5_pcie_window_plan plan;
    assert(!rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&plan));
    struct rpi5_fdt_memory ram={{0,0x40000000,0x100000000},{0x3f800000,0x100000000,0x200000000},3};
    struct rpi5_reservation_plan reserved={0};
    reserved.fixed.extent[0]=(struct rpi5_range){0,0x80000};reserved.fixed.count=1;
    reserved.count=1;reserved.request[0].size=0x4000000;reserved.request[0].window_count=1;
    reserved.request[0].window[0]=(struct rpi5_range){0,0x40000000};
    struct rpi5_gem_dma_route result,before;
    assert(!rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0x100000000,0x48000,&result));
    assert(result.physical==0x100000000 && result.pci==0x1100000000 && result.rp1==result.pci && result.bytes==0x48000);
    /* Every value bit of every encoded-plan byte except structure padding is
     * tested by independently replacing the exact scalar fields below. */
    unsigned failures=0;
#define BAD(expr) do { memset(&result,0xa5,sizeof result);before=result;assert((expr)!=0);assert(!memcmp(&result,&before,sizeof result));failures++; } while(0)
    const uint64_t addresses[]={0,1,0x7ffff,0x80000,0x3f7fc000,0x3f800000,0x1ffffc000,0x200000000,
        0x1000130000,0x1f00000000,0xc040000000,UINT64_MAX};
    for (unsigned i=0;i<sizeof addresses/sizeof *addresses;i++)
        BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,addresses[i],0x48000,&result));
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0x100000000,0,&result));
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0x100000000,UINT64_MAX,&result));
    for(unsigned i=0;i<3;i++)for(unsigned bit=0;bit<64;bit++) {
        struct rpi5_pcie_window_plan changed=plan;
        changed.inbound[i].cpu_base^=UINT64_C(1)<<bit;
        BAD(rpi5_gem_dma_route(&f,&changed,&ram,&reserved,0,0x100000000,0x48000,&result));
        changed=plan;changed.inbound[i].pci_base^=UINT64_C(1)<<bit;
        BAD(rpi5_gem_dma_route(&f,&changed,&ram,&reserved,0,0x100000000,0x48000,&result));
        changed=plan;changed.inbound[i].size^=UINT64_C(1)<<bit;
        BAD(rpi5_gem_dma_route(&f,&changed,&ram,&reserved,0,0x100000000,0x48000,&result));
    }
    for(unsigned i=0;i<3;i++)for(unsigned bit=0;bit<32;bit++) {
#define CHANGED(field) do {struct rpi5_pcie_window_plan changed=plan;changed.inbound[i].field^=UINT32_C(1)<<bit;BAD(rpi5_gem_dma_route(&f,&changed,&ram,&reserved,0,0x100000000,0x48000,&result));}while(0)
        CHANGED(bar_lo);CHANGED(bar_hi);CHANGED(remap_lo);CHANGED(remap_hi);
#undef CHANGED
    }
    for(unsigned i=0;i<3;i++) {
        struct rpi5_pcie_fdt changed=f;
        changed.rp1_dma[0]=f.rp1_dma[i];
        if(i) BAD(rpi5_gem_dma_route(&changed,&plan,&ram,&reserved,0,0x100000000,0x48000,&result));
    }
    struct rpi5_range initrd={0x100020000,0x100024000};
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,&initrd,0x100000000,0x48000,&result));
    reserved.fixed.extent[1]=initrd;reserved.fixed.count=2;
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0x100000000,0x48000,&result));
    reserved.fixed.count=1;reserved.request[0].window_count=0;
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0x100000000,0x48000,&result));
    reserved.count=0;
    assert(!rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0xffff0000,0x48000,&result)); /* adjacent RAM banks */
    ram.start[2]++;
    BAD(rpi5_gem_dma_route(&f,&plan,&ram,&reserved,0,0xffff0000,0x48000,&result));
    printf("DMA_ROUTE_PASS negatives=%u NO_LIVE_DMA_AUTHORITY\n",failures);
    return 0;
}
