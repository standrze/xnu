/* SPDX-License-Identifier: BSD-2-Clause */
#include "reservation_record.h"
#define LIMIT (UINT64_C(1)<<40)
static int range(uint64_t a,uint64_t b){return a<b && b<=LIMIT;}
static int overlap(uint64_t a,uint64_t b,uint64_t c,uint64_t d){return a<d && c<b;}
static int zero(const void *p,size_t n){const uint8_t *b=p;for(size_t i=0;i<n;i++)if(b[i])return 0;return 1;}
static uint64_t le(const uint8_t *p){uint64_t v=0;for(unsigned i=0;i<8;i++)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v){for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(v>>(8*i));}
static int alias(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na>UINTPTR_MAX-x||nb>UINTPTR_MAX-y||(x<y+nb&&y<x+na);}
int rpi5_reservation_record_fixed(const struct rpi5_reservation_plan *p,struct rpi5_ranges *out)
{
    if(!p||!out||p->fixed.count>32)return -1;
    struct rpi5_ranges r={0};
    for(size_t i=0;i<p->fixed.count;i++){
        struct rpi5_range v=p->fixed.extent[i];if(!range(v.start,v.end))return -1;
        size_t at=r.count;while(at && r.extent[at-1].start>v.start){r.extent[at]=r.extent[at-1];at--;}
        r.extent[at]=v;r.count++;
    }
    size_t n=0;
    for(size_t i=0;i<r.count;i++){
        if(n && r.extent[i].start<=r.extent[n-1].end){if(r.extent[i].end>r.extent[n-1].end)r.extent[n-1].end=r.extent[i].end;}
        else r.extent[n++]=r.extent[i];
    }
    for(size_t i=n;i<32;i++)r.extent[i]=(struct rpi5_range){0,0};
    r.count=n;*out=r;return 0;
}
int rpi5_reservation_record_valid(const struct rpi5_reservation_record *r)
{
    if(!r||r->fixed_count>32||r->dynamic_count>8||
        r->managed_start!=0x6000000||r->managed_end!=0x10000000||
        r->loader_start!=0x9000000||!range(r->loader_start,r->loader_end)||
        r->kernel_start!=0x7004000||!range(r->kernel_start,r->kernel_end)||
        r->kernel_end>r->args_pa||r->args_pa!=((r->kernel_end+16383)&~UINT64_C(16383))||
        r->args_bytes!=1152||r->tree_pa!=r->args_pa+16384||!r->tree_bytes||r->tree_bytes>16384||
        r->tree_pa+r->tree_bytes>r->loader_start||r->fdt_pa<r->loader_end||(r->fdt_pa&7)||
        r->fdt_bytes<40||r->fdt_bytes>1048576||r->fdt_pa>r->top||r->fdt_bytes>r->top-r->fdt_pa||
        !r->owner_counter||(r->top&16383)||r->top>r->managed_end||r->top<=r->loader_end||
        zero(r->fdt_sha256,32))return -1;
    for(size_t i=0;i<32;i++){
        const struct rpi5_range *f=&r->fixed[i];
        if(i>=r->fixed_count){if(f->start||f->end)return -1;continue;}
        if(!range(f->start,f->end)||(i && r->fixed[i-1].end>=f->start)||
            overlap(f->start,f->end,r->managed_start,r->managed_end))return -1;
    }
    for(size_t i=0;i<8;i++){
        const struct rpi5_reservation_claim *d=&r->dynamic[i];
        if(i>=r->dynamic_count){if(d->node_offset||d->no_map||d->start||d->end||d->alignment)return -1;continue;}
        if(!d->node_offset||d->node_offset>UINT32_MAX||d->no_map>1||!range(d->start,d->end)||
            !d->alignment||(d->alignment&(d->alignment-1))||(d->start&(d->alignment-1))||
            overlap(d->start,d->end,r->managed_start,r->managed_end))return -1;
        for(size_t j=0;j<r->fixed_count;j++)if(overlap(d->start,d->end,r->fixed[j].start,r->fixed[j].end))return -1;
        for(size_t j=0;j<i;j++)if(d->node_offset==r->dynamic[j].node_offset||
            overlap(d->start,d->end,r->dynamic[j].start,r->dynamic[j].end))return -1;
    }
    return 0;
}
int rpi5_reservation_record_encode(const struct rpi5_reservation_record *r,void *out,size_t bytes)
{
    if(!out||bytes!=RPI5_RESERVATION_RECORD_BYTES||rpi5_reservation_record_valid(r)||alias(r,sizeof *r,out,bytes))return -1;
    uint8_t raw[RPI5_RESERVATION_RECORD_BYTES]={0};
    const uint64_t words[]={RPI5_RESERVATION_RECORD_MAGIC,1,RPI5_RESERVATION_RECORD_BYTES,1,r->fixed_count,r->dynamic_count,
        r->managed_start,r->managed_end,r->loader_start,r->loader_end,r->fdt_pa,r->fdt_bytes,r->args_pa,r->args_bytes,
        r->tree_pa,r->tree_bytes,r->top,r->kernel_start,r->kernel_end,r->owner_counter,16384,32,8,0};
    for(unsigned i=0;i<24;i++)put(raw+8*i,words[i]);
    for(unsigned i=0;i<32;i++)raw[192+i]=r->fdt_sha256[i];
    for(unsigned i=0;i<32;i++){put(raw+224+16*i,r->fixed[i].start);put(raw+232+16*i,r->fixed[i].end);}
    for(unsigned i=0;i<8;i++){
        const struct rpi5_reservation_claim *d=&r->dynamic[i];
        const uint64_t fields[]={d->node_offset,d->no_map,d->start,d->end,d->alignment};
        for(unsigned j=0;j<5;j++)put(raw+736+40*i+8*j,fields[j]);
    }
    uint8_t *p=out;for(unsigned i=0;i<sizeof raw;i++)p[i]=raw[i];return 0;
}
int rpi5_reservation_record_decode(const void *data,size_t bytes,struct rpi5_reservation_record *out)
{
    if(!data||!out||bytes!=RPI5_RESERVATION_RECORD_BYTES||alias(data,bytes,out,sizeof *out))return -1;
    const uint8_t *p=data;
    if(le(p)!=RPI5_RESERVATION_RECORD_MAGIC||le(p+8)!=1||le(p+16)!=bytes||le(p+24)!=1||
        le(p+160)!=16384||le(p+168)!=32||le(p+176)!=8||le(p+184))return -1;
    struct rpi5_reservation_record r={0};
    uint64_t *fields[]={&r.fixed_count,&r.dynamic_count,&r.managed_start,&r.managed_end,&r.loader_start,&r.loader_end,
        &r.fdt_pa,&r.fdt_bytes,&r.args_pa,&r.args_bytes,&r.tree_pa,&r.tree_bytes,&r.top,&r.kernel_start,&r.kernel_end,&r.owner_counter};
    for(unsigned i=0;i<16;i++)*fields[i]=le(p+32+8*i);
    for(unsigned i=0;i<32;i++)r.fdt_sha256[i]=p[192+i];
    for(unsigned i=0;i<32;i++)r.fixed[i]=(struct rpi5_range){le(p+224+16*i),le(p+232+16*i)};
    for(unsigned i=0;i<8;i++)r.dynamic[i]=(struct rpi5_reservation_claim){le(p+736+40*i),le(p+744+40*i),
        le(p+752+40*i),le(p+760+40*i),le(p+768+40*i)};
    if(rpi5_reservation_record_valid(&r))return -1;
    *out=r;return 0;
}
int rpi5_reservation_record_source(const void *data,size_t bytes,struct rpi5_fdt_memory *ram,
    struct rpi5_reservation_plan *out)
{
    if(!ram||!out)return -1;
    struct rpi5_fdt_memory m;struct rpi5_reservation_plan p;
    if(rpi5_fdt_memory(data,bytes,&m)||rpi5_fdt_reservation_plan(data,bytes,&p)||p.fixed.count>=32)return -1;
    p.fixed.extent[p.fixed.count++]=(struct rpi5_range){0,0x80000};
    struct rpi5_range initrd;int rc=rpi5_fdt_initrd(data,bytes,&initrd);
    if(rc<0)return -1;
    if(!rc){if(p.fixed.count>=32||initrd.start<0x80000)return -1;p.fixed.extent[p.fixed.count++]=initrd;}
    *ram=m;*out=p;return 0;
}
int rpi5_reservation_record_validate_fdt(const struct rpi5_reservation_record *r,const void *data,size_t bytes)
{
    if(rpi5_reservation_record_valid(r)||r->fdt_bytes!=bytes)return -1;
    struct rpi5_fdt_memory ram;struct rpi5_reservation_plan p;struct rpi5_ranges fixed;
    if(rpi5_reservation_record_source(data,bytes,&ram,&p)||rpi5_reservation_record_fixed(&p,&fixed)||
        fixed.count!=r->fixed_count||p.count!=r->dynamic_count)return -1;
    for(size_t i=0;i<fixed.count;i++)if(fixed.extent[i].start!=r->fixed[i].start||fixed.extent[i].end!=r->fixed[i].end)return -1;
    struct rpi5_range memory[8];for(unsigned i=0;i<ram.count;i++)memory[i]=(struct rpi5_range){ram.start[i],ram.end[i]};
    const struct rpi5_range covered[]={
        {r->managed_start,r->managed_end},{r->loader_start,r->loader_end},
        {r->fdt_pa,r->fdt_pa+r->fdt_bytes},{r->args_pa,r->args_pa+r->args_bytes},
        {r->tree_pa,r->tree_pa+r->tree_bytes},{r->kernel_start,r->kernel_end}};
    /* Managed includes the live spans: validate each independently, not as
     * pairwise-disjoint allocations. The actual handoff planner proves that. */
    for(unsigned i=0;i<sizeof covered/sizeof covered[0];i++)
        if(rpi5_ranges_validate_live(memory,ram.count,&covered[i],1))return -1;
    struct rpi5_resolved_reservations replay;
    const struct rpi5_range owner_live[]={{r->loader_start,r->loader_end},{r->fdt_pa,r->fdt_pa+r->fdt_bytes}};
    if(rpi5_resolve_reservations(&ram,&p,owner_live,2,&replay)||
        rpi5_ranges_validate_live(replay.reservation_free.extent,replay.reservation_free.count,owner_live,2)||
        rpi5_ranges_validate_live(replay.reservation_free.extent,replay.reservation_free.count,covered,1))return -1;
    for(unsigned i=0;i<p.count;i++){
        const struct rpi5_dynamic_reservation *q=&p.request[i];const struct rpi5_reservation_claim *d=&r->dynamic[i];
        if(d->node_offset!=q->node_offset||d->no_map!=q->no_map||d->alignment!=q->alignment||
            d->end-d->start!=q->size||!q->window_count||q->window_count>8||
            d->start!=replay.allocation[i].start||d->end!=replay.allocation[i].end)return -1;
        struct rpi5_range live={d->start,d->end};
        if(rpi5_ranges_validate_live(memory,ram.count,&live,1))return -1;
        unsigned found=0;for(unsigned j=0;j<q->window_count;j++)if(q->window[j].start<=d->start&&q->window[j].end>=d->end)found++;
        if(!found)return -1;
    }
    return 0;
}
