/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_reservation_kernel.h"
int rpi5_reservation_kernel_validate(const void *wire,size_t wire_bytes,const void *fdt,size_t fdt_bytes,
    const struct rpi5_reservation_boot_context *c,const uint8_t digest[32],struct rpi5_reservation_record *out)
{
    if(!c||!digest||!out)return -1;
    struct rpi5_reservation_record r;
    if(rpi5_reservation_record_decode(wire,wire_bytes,&r)||
        rpi5_reservation_record_validate_fdt(&r,fdt,fdt_bytes)||
        r.managed_start!=c->managed_start||r.managed_end!=c->managed_end||
        r.loader_start!=c->loader_start||r.loader_end!=c->loader_end||
        r.fdt_pa!=c->fdt_pa||r.fdt_bytes!=c->fdt_bytes||
        r.args_pa!=c->args_pa||r.args_bytes!=c->args_bytes||r.tree_pa!=c->tree_pa||r.tree_bytes!=c->tree_bytes||
        r.top!=c->top||r.kernel_start!=c->kernel_start||r.kernel_end!=c->kernel_end||
        !c->counter||r.owner_counter>c->counter)return -1;
    unsigned different=0;for(unsigned i=0;i<32;i++)different|=r.fdt_sha256[i]^digest[i];
    if(different)return -1;
    *out=r;return 0;
}
int rpi5_reservation_kernel_buffer(const struct rpi5_reservation_record *r,uint64_t p,uint64_t n)
{
    if(rpi5_reservation_record_valid(r)||!n||p<r->managed_start||p>=r->managed_end||n>r->managed_end-p)return -1;
    /* The complete loaded kernel and retained boot tail are never DMA-buffer
     * candidates, even if a forged standalone numeric span fits installed RAM.
     * Reclaimed pre-kernel pages are only eligible via genuine VM allocation. */
    if(p<r->top&&r->kernel_start<p+n)return -1;
    for(unsigned i=0;i<r->fixed_count;i++)if(p<r->fixed[i].end&&r->fixed[i].start<p+n)return -1;
    for(unsigned i=0;i<r->dynamic_count;i++)if(p<r->dynamic[i].end&&r->dynamic[i].start<p+n)return -1;
    return 0;
}
