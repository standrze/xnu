/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_compact_adapter.h"
static uint8_t fresh_copy[1048576];
static struct {
    const void *original;size_t bytes;
    uint64_t affinity,frequency,start,absolute_deadline;
    uint32_t used,active,stores,barriers;
    struct rpi5_display_allocate_result allocated;
    struct rpi5_display_allocate_report allocation;
    struct rpi5_display_retained retained;
} owner;
static int same(const void *a,const void *b,size_t n)
{const uint8_t *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&!(x<y+nb&&y<x+na);}
static int machine(void)
{
    struct rpi5_display_query_registers r;rpi5_display_query_registers(&r);
    return r.el==4&&!(r.sctlr&UINT64_C(0x02001005))&&(r.daif&0x3c0)==0x3c0&&
        (r.mpidr&UINT64_C(0xff00ffffff))==owner.affinity&&r.frequency==owner.frequency&&
        r.frequency>=1000000&&r.frequency<=1000000000&&
        (r.midr&UINT64_C(0xff0ffff0))==UINT64_C(0x410fd0b0)&&
        (r.ctr&UINT64_C(0xf000f))==UINT64_C(0x40004);
}
static int current(void *context)
{return !(context==&owner&&owner.used==1&&owner.active==1&&machine()&&same(owner.original,fresh_copy,owner.bytes));}
static int now_us(void *context,uint64_t *out)
{
    if(context!=&owner||!out||!owner.active||!machine())return -1;
    uint64_t n=rpi5_display_query_counter();
    if(n<owner.start||n>=owner.absolute_deadline||n-owner.start>UINT64_MAX/1000000)return -1;
    *out=(n-owner.start)*1000000/owner.frequency;return 0;
}
static int store(void *context,uint64_t address,uint32_t value)
{
    unsigned n=owner.stores;
    if(context!=&owner||!owner.active||n>=RPI5_COMPACT_STORES||!machine())return -1;
    unsigned x=n%96,y=n/96;
    uint64_t expected=owner.retained.framebuffer.allocation.start+(y+16)*7680+(x+16)*4;
    if(address!=expected||(address&3)||address+4>owner.retained.framebuffer.allocation.end||
        value!=rpi5_display_compact_pixel(x,y))return -1;
    owner.stores++;rpi5_display_compact_store((uintptr_t)address,value);
    return machine()?0:-1;
}
static int barrier(void *context)
{
    if(context!=&owner||!owner.active||owner.barriers>=8||owner.stores!=(owner.barriers+1)*96||!machine())return -1;
    owner.barriers++;rpi5_display_compact_barrier();return machine()?0:-1;
}
int rpi5_display_compact_run(const void *original,size_t bytes,struct rpi5_range image,
    void *storage,uint64_t affinity,uint64_t absolute_deadline,
    struct rpi5_display_allocate_result *allocated,struct rpi5_display_allocate_report *allocation,
    struct rpi5_display_compact_report *draw)
{
    if(owner.used||!original||bytes<40||bytes>sizeof fresh_copy||!storage||!allocated||!allocation||!draw||
        !apart(allocated,sizeof *allocated,allocation,sizeof *allocation)||!apart(allocated,sizeof *allocated,draw,sizeof *draw)||
        !apart(allocation,sizeof *allocation,draw,sizeof *draw)||!apart(draw,sizeof *draw,original,bytes)||
        !apart(draw,sizeof *draw,storage,16384)||!apart(allocated,sizeof *allocated,original,bytes)||
        !apart(allocation,sizeof *allocation,original,bytes)||!apart(allocated,sizeof *allocated,storage,16384)||
        !apart(allocation,sizeof *allocation,storage,16384))return -1;
    owner.used=1;owner.original=original;owner.bytes=bytes;owner.affinity=affinity;owner.absolute_deadline=absolute_deadline;
    struct rpi5_display_query_registers registers;rpi5_display_query_registers(&registers);owner.frequency=registers.frequency;
    *draw=(struct rpi5_display_compact_report){.result=-2};
    uint64_t f=rpi5_display_query_identity(original);
    if(!machine()||image.start!=0x9000000||image.end<=image.start||image.end>UINT64_C(0x100000000)||
        f<0x80000||(f&7)||f>UINT32_MAX||bytes>UINT64_C(0x100000000)-f||
        (f<image.end&&image.start<f+bytes))return -1;
    for(size_t i=0;i<bytes;i++)fresh_copy[i]=((const uint8_t *)original)[i];
    if(!same(original,fresh_copy,bytes))return -1;
    int rc=rpi5_display_allocate_run(original,bytes,image,storage,affinity,&owner.allocated,&owner.allocation);
    if(!rc){
        owner.start=rpi5_display_query_counter();owner.active=1;
        if(current(&owner)||owner.start>=absolute_deadline||
            rpi5_display_allocation_retained(&owner.allocated,&owner.allocation,fresh_copy,bytes,
                rpi5_display_query_identity(original),image,0,0,&owner.retained))draw->result=-3;
        else {
            struct rpi5_display_compact_ops ops={&owner,current,now_us,store,barrier};
            (void)rpi5_display_compact_patch(&owner.retained,&ops,draw);
            if(!draw->result&&(owner.stores!=RPI5_COMPACT_STORES||owner.barriers!=8||current(&owner)))draw->result=-4;
        }
        owner.active=0;
    }
    *allocation=owner.allocation;
    if(!rc)*allocated=owner.allocated;
    return rc;
}

