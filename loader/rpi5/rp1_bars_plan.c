/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_bars_plan.h"
#define LIMIT (UINT64_C(1)<<40)
#define MEM32 UINT32_C(0x02000000)
static int span(uint64_t base,uint64_t size,uint64_t limit)
{ return size && base<limit && size<=limit-base; }
static int pages(uint64_t base,uint64_t size,uint64_t offset,uint64_t length,
    struct rpi5_range *out)
{
    if(!span(offset,length,size))return -1;
    uint64_t start=(base+offset)&~UINT64_C(0x3fff);
    uint64_t end=(base+offset+length+0x3fff)&~UINT64_C(0x3fff);
    if(start<base || end>base+size || start>=end)return -1;
    *out=(struct rpi5_range){start,end};return 0;
}
int rpi5_rp1_bars_assignment_plan(const struct rpi5_pcie_fdt *f,
    const struct rpi5_rp1_bars_probe *s,const struct rpi5_rp1_bars_size *sizes,
    struct rpi5_rp1_bars_plan *out)
{
    if(!f || !s || !sizes || !out || s->state!=RPI5_RP1_BARS_COMPLETE ||
        s->transactions!=49 || s->writes_started!=12 || s->selected!=5 ||
        sizes->transactions!=49 || (sizes->command&~UINT32_C(0xfff8)) || (sizes->present&~63u) ||
        !(sizes->present&2) || !f->outbound_count || f->outbound_count>2 ||
        f->rp1_pci_base || !f->rp1_aperture_size)return -1;
    const struct rpi5_pcie_window *window=0;
    for(unsigned i=0;i<f->outbound_count;i++) {
        const struct rpi5_pcie_window *w=&f->outbound[i];
        if((w->space!=MEM32 && w->space!=UINT32_C(0x43000000)) ||
            !span(w->pci_base,w->size,w->space==MEM32?(UINT64_C(1)<<32):LIMIT) ||
            !span(w->cpu_base,w->size,LIMIT) || ((w->cpu_base|w->pci_base)&0xfffff))return -1;
        if(i && w->cpu_base<f->outbound[0].cpu_base+f->outbound[0].size &&
            f->outbound[0].cpu_base<w->cpu_base+w->size)return -1;
        if(i && w->pci_base<f->outbound[0].pci_base+f->outbound[0].size &&
            f->outbound[0].pci_base<w->pci_base+w->size)return -1;
        if(w->space==MEM32) {if(window)return -1;window=w;}
    }
    if(!window || window->pci_base || (window->cpu_base&0x3fff) ||
        f->rp1_aperture_size>window->size)return -1;
    struct rpi5_rp1_bars_plan result={0};result.present=sizes->present;
    uint32_t remaining=sizes->present;
    for(unsigned i=0;i<6;i++) {
        const struct rpi5_rp1_bar_size *b=&sizes->bar[i];
        if(b->original!=s->originals[i] || (b->original&15) || (b->mask&15))return -1;
        if(!(remaining&(1u<<i))) {if(b->mask || b->size || b->original)return -1;continue;}
        if(!b->mask || b->size<16 || (b->size&(b->size-1)) ||
            (uint32_t)(~b->mask+1u)!=b->size || (b->original&(b->size-1)))return -1;
    }
    uint64_t cursor=0;
    for(unsigned pass=0;pass<6 && remaining;pass++) {
        unsigned selected=1;
        if(pass) {
            selected=6;
            for(unsigned i=0;i<6;i++)if((remaining&(1u<<i)) &&
                (selected==6 || sizes->bar[i].size>sizes->bar[selected].size))selected=i;
        }
        if(selected>=6 || !(remaining&(1u<<selected)))return -1;
        uint64_t size=sizes->bar[selected].size;
        uint64_t base=(cursor+size-1)&~(size-1);
        if(!span(base,size,UINT64_C(1)<<32) || base>=window->size || size>window->size-base)return -1;
        result.pci_base[selected]=(uint32_t)base;
        result.cpu[selected]=(struct rpi5_range){window->cpu_base+base,window->cpu_base+base+size};
        cursor=base+size;remaining&=~(1u<<selected);
    }
    if(remaining || result.pci_base[1] ||
        !span(f->gem_bar_offset,f->gem_size,f->rp1_aperture_size) ||
        !span(f->clock_bar_offset,f->clock_size,f->rp1_aperture_size) ||
        pages(window->cpu_base,sizes->bar[1].size,f->gem_bar_offset,f->gem_size,&result.gem_pages) ||
        pages(window->cpu_base,sizes->bar[1].size,f->clock_bar_offset,f->clock_size,&result.clock_pages) ||
        (result.gem_pages.start<result.clock_pages.end &&
         result.clock_pages.start<result.gem_pages.end))return -1;
    *out=result;return 0;
}
