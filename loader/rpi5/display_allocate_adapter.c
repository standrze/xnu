/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_allocate_adapter.h"

/* Only this image ever uses these objects. The copy is made from the fresh
 * original entry FDT; it is private, never handed to firmware and never
 * mutated after parsing. No dynamic reserved-memory requests are allocated. */
static uint8_t original_copy[1048576];
static struct rpi5_fdt_memory ram;
static struct rpi5_reservation_plan reservations;
static struct {
    const void *original;
    size_t bytes;
    struct rpi5_range image;
    struct rpi5_display_mailbox_fdt binding;
    struct rpi5_display_mailbox_buffer buffers[4];
    struct rpi5_display_mailbox_session session;
    struct rpi5_display_allocate_result result;
    uint64_t owner,affinity,frequency,start;
    uint32_t used,active,cache_operations,reads,writes;
} context;
static int same(const void *a,const void *b,size_t n)
{const uint8_t *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static int overlap(uint64_t a,uint64_t ae,uint64_t b,uint64_t be)
{return a<be&&b<ae;}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x && nb<=UINTPTR_MAX-y && !overlap(x,x+na,y,y+nb);}
static int machine(void)
{
    struct rpi5_display_query_registers r;
    rpi5_display_query_registers(&r);
    /* A76 implementer/architecture/part exact, revision/variant immaterial.
     * Both DminLine/IminLine=4 (64B); unknown CPU/line sizes rejected. */
    return r.el==4 && !(r.sctlr&UINT64_C(0x02001005)) &&
        (r.daif&0x3c0)==0x3c0 && (r.mpidr&UINT64_C(0xff00ffffff))==context.affinity &&
        r.frequency==context.frequency && r.frequency>=1000000 && r.frequency<=1000000000 &&
        (r.midr&UINT64_C(0xff0ffff0))==UINT64_C(0x410fd0b0) &&
        (r.ctr&UINT64_C(0xf000f))==UINT64_C(0x40004);
}
static int current(void *opaque,const struct rpi5_display_mailbox_session *s,
    const struct rpi5_display_mailbox_fdt *binding,
    const struct rpi5_display_mailbox_buffer *buffers,uint64_t owner)
{
    return !(opaque==&context && context.used==1 && context.active==1 &&
        s==&context.session && binding==&context.binding && buffers==context.buffers &&
        owner==context.owner && owner && machine());
}
static int buffer_ok(unsigned slot,const struct rpi5_display_mailbox_buffer *b)
{
    if(slot>=4 || b!=&context.buffers[slot] || b->capacity!=4096 ||
        rpi5_display_query_identity(b->cpu)!=b->mailbox_address || (b->mailbox_address&4095) ||
        b->mailbox_address<context.image.start || b->mailbox_address+4096>context.image.end ||
        b->mailbox_address>UINT64_C(0xfffff000))return 0;
    return 1;
}
static int admit(void *opaque,unsigned slot,const struct rpi5_display_mailbox_buffer *b,
    const struct rpi5_display_mailbox_fdt *binding)
{
    return !(opaque==&context && binding==&context.binding && buffer_ok(slot,b) &&
        !(context.session.tx_attempted&(1u<<slot)) &&
        same(context.original,original_copy,context.bytes));
}
static int now_us(void *opaque,uint64_t *out)
{
    if(opaque!=&context || !out)return -1;
    uint64_t ticks=rpi5_display_query_counter();
    if(ticks<context.start)return -1;
    ticks-=context.start;
    if(ticks>UINT64_MAX/1000000)return -1;
    *out=ticks*1000000/context.frequency;return 0;
}
static int read32(void *opaque,uint32_t offset,uint32_t *out)
{
    if(opaque!=&context || !out || (offset!=0 && offset!=0x10 && offset!=0x18 && offset!=0x38))return -1;
    uint32_t value=rpi5_display_query_read((uintptr_t)context.binding.mmio.start+offset);
    context.reads++;
    /* Spread the finite512 status polls over at most512ms instead of burning
     * through them before VideoCore can respond. No extra MMIO: bounded
     * counter-only wait, global core deadline still brackets this callback. */
    if((offset==0x18 && (value&RPI5_DISPLAY_MBOX_EMPTY)) ||
        (offset==0x38 && (value&RPI5_DISPLAY_MBOX_FULL))){
        uint64_t start=rpi5_display_query_counter(),ticks=context.frequency/1000;
        int finished=0;
        for(unsigned i=0;i<1000000;i++){
            uint64_t n=rpi5_display_query_counter();
            if(n<start)return -1;
            if(n-start>=ticks){finished=1;break;}
        }
        if(!finished)return -1;
    }
    *out=value;return 0;
}
static int write32(void *opaque,uint32_t offset,uint32_t value)
{
    unsigned slot=context.session.slot;
    if(opaque!=&context || offset!=0x20 || slot>=4 || context.writes>=4 ||
        value!=((uint32_t)context.buffers[slot].mailbox_address|8u))return -1;
    context.writes++;
    rpi5_display_query_write((uintptr_t)context.binding.mmio.start+offset,value);return 0;
}
static int cache(void *opaque,unsigned slot,const struct rpi5_display_mailbox_buffer *b,
    size_t bytes,enum rpi5_display_mailbox_cache operation)
{
    if(opaque!=&context || !buffer_ok(slot,b) || (bytes!=28 && bytes!=104 && bytes!=184 && bytes!=240))return -1;
    if(operation==RPI5_DISPLAY_MBOX_PUBLISH)rpi5_display_query_clean((uintptr_t)b->cpu);
    else if(operation==RPI5_DISPLAY_MBOX_ACQUIRE)rpi5_display_query_invalidate((uintptr_t)b->cpu);
    else return -1;
    context.cache_operations++;return 0;
}
static int candidate(struct rpi5_display_allocate_candidate *out)
{
    const struct rpi5_display_allocate_reply *a=&context.result.reply[2];
    uint64_t bus=a->words[13],size=a->words[14];
    /* Pi5 EDK2 RPi5.dsc PcdDmaDeviceOffset=0xc0000000 and
     * RpiFirmwareAllocFb clears that mask. Only its explicit C alias is
     * admitted here; no generic masked pointer or DW64-address inference. */
    if((bus&UINT64_C(0xc0000000))!=UINT64_C(0xc0000000))return -1;
    uint64_t base=bus&UINT64_C(0x3fffffff),end=base+size;
    if(!base||(base&16383)||size<8294400||size>16*1024*1024||end<=base||end>0x40000000)return -1;
    uint64_t low=0;
    for(unsigned i=0;i<ram.count;i++){
        if(!ram.start[i]){if(low)return -1;low=ram.end[i];}
        if(overlap(base,end,ram.start[i],ram.end[i]))return -1;
    }
    /* Pi5-specific memory model: firmware reserves the tail below1GiB.
     * Fresh FDT bounds this hole; a hole alone is NOT an allocation proof.
     * Exact successful ALLOCATE plus matching GET is also mandatory. */
    if(low<0x3e000000||low>0x3fc00000||base<low)return -1;
    uint64_t re=(end+16383)&~UINT64_C(16383);
    if(re>0x40000000||overlap(base,re,context.image.start,context.image.end))return -1;
    for(unsigned i=0;i<ram.count;i++)
        if(overlap(base,re,ram.start[i],ram.end[i]))return -1;
    uint64_t f=rpi5_display_query_identity(context.original),fe=f+context.bytes;
    if(overlap(base,re,f,fe)||overlap(base,re,f&~UINT64_C(0x1fffff),(f&~UINT64_C(0x1fffff))+0x400000))return -1;
    for(size_t i=0;i<reservations.fixed.count;i++)
        if(overlap(base,re,reservations.fixed.extent[i].start,reservations.fixed.extent[i].end))return -1;
    struct rpi5_range initrd;int rc=rpi5_fdt_initrd(original_copy,context.bytes,&initrd);
    if(rc!=1&&(rc||overlap(base,re,initrd.start,initrd.end)))return -1;
    *out=(struct rpi5_display_allocate_candidate){bus,base,size,base,re,1920,1080,7680,32,0,2};
    return 0;
}
int rpi5_display_allocate_run(const void *original,size_t bytes,struct rpi5_range image,
    void *storage,uint64_t affinity,struct rpi5_display_allocate_result *out,
    struct rpi5_display_allocate_report *report)
{
    if(context.used || !original || !storage || !out || !report || !bytes || bytes>sizeof original_copy ||
        !apart(out,sizeof *out,report,sizeof *report) || !apart(out,sizeof *out,storage,16384) ||
        !apart(report,sizeof *report,storage,16384) || !apart(out,sizeof *out,original,bytes) ||
        !apart(report,sizeof *report,original,bytes))return -1;
    context.used=1; /* An attempted admission is also one-shot. */
    context.original=original;context.bytes=bytes;context.image=image;context.affinity=affinity;
    struct rpi5_display_query_registers regs;rpi5_display_query_registers(&regs);
    context.frequency=regs.frequency;
    /* Actual linked identity leaf is exactly RET: it never translates or
     * masks an address. Host tests double only this architecture boundary. */
    uint64_t p=rpi5_display_query_identity(storage),f=rpi5_display_query_identity(original),fe=f+bytes;
    uint64_t mapped_fdt=f&~UINT64_C(0x1fffff);
    if(!machine() || image.start!=UINT64_C(0x9000000) || image.end<=image.start || image.end>UINT64_C(0x100000000) ||
        (p&4095) || p<image.start || p>image.end || image.end-p<16384 ||
        f<0x80000 || f>UINT32_MAX || fe<f || fe>UINT64_C(0x100000000) ||
        overlap(image.start,image.end,f,fe) || overlap(p,p+16384,mapped_fdt,mapped_fdt+0x400000))return -1;
    for(size_t i=0;i<bytes;i++)original_copy[i]=((const uint8_t *)original)[i];
    if(!same(original,original_copy,bytes) || rpi5_display_mailbox_from_fdt(original_copy,bytes,&context.binding) ||
        rpi5_fdt_memory(original_copy,bytes,&ram) || rpi5_fdt_reservation_plan(original_copy,bytes,&reservations))return -1;
    struct rpi5_range initrd,live[]={image,{f,fe}},ranges[8];
    int ir=rpi5_fdt_initrd(original_copy,bytes,&initrd);
    if(ir!=1 && (ir || overlap(image.start,image.end,initrd.start,initrd.end) || overlap(f,fe,initrd.start,initrd.end)))return -1;
    for(unsigned i=0;i<ram.count;i++)ranges[i]=(struct rpi5_range){ram.start[i],ram.end[i]};
    if(rpi5_ranges_validate_live(ranges,ram.count,live,2))return -1;
    for(size_t i=0;i<reservations.fixed.count;i++)for(unsigned j=0;j<2;j++)
        if(overlap(live[j].start,live[j].end,reservations.fixed.extent[i].start,reservations.fixed.extent[i].end))return -1;
    for(unsigned i=0;i<4;i++)context.buffers[i]=(struct rpi5_display_mailbox_buffer){(uint8_t *)storage+4096*i,4096,p+4096*i};
    context.start=rpi5_display_query_counter();context.owner=context.start?context.start:1;context.active=1;
    /* No prior NS cacheable client under the pinned direct-reset lineage;
     * discard any stale local lines before creating requests. Full pages,
     * no false sharing, no EL3 FDT-window alias, no later cache enable. */
    int rc=-7;struct rpi5_display_allocate_candidate fb={0};
    for(unsigned i=0;i<4;i++){
        if(current(&context,&context.session,&context.binding,context.buffers,context.owner))goto failed;
        rpi5_display_query_invalidate((uintptr_t)context.buffers[i].cpu);context.cache_operations++;
        if(current(&context,&context.session,&context.binding,context.buffers,context.owner))goto failed;
    }
    struct rpi5_display_mailbox_ops ops={&context,current,admit,now_us,read32,write32,cache};
    rc=rpi5_display_allocate_exchange(&context.session,&context.binding,context.buffers,&ops,context.owner,1000000,&context.result);
    if(!same(original,original_copy,bytes) || !machine())rc=-7;
    if(!rc && candidate(&fb))rc=-8;
failed:
    if(rc){context.session.state=RPI5_DISPLAY_MBOX_QUARANTINED;context.session.busy=0;
        context.session.quarantined_buffers=15;context.session.error=rc;}
    context.active=0;
    *report=(struct rpi5_display_allocate_report){.binding=context.binding,.session=context.session,
        .buffer_address={p,p+4096,p+8192,p+12288},.counter_start=context.start,.admission=1,
        .cache_operations=context.cache_operations,.mmio_reads=context.reads,.mmio_writes=context.writes,.result=rc};
    static const size_t wire_bytes[]={104,28,184,240};
    for(unsigned i=0;i<4;i++)if(context.session.completed&(1u<<i)){
        if(!rpi5_display_allocate_response(i+1,context.buffers[i].cpu,wire_bytes[i],&report->replies[i]))report->decoded_replies|=1u<<i;
    }
    if(!rc){report->candidate=fb;report->candidate_valid=1;*out=context.result;}
    return rc;
}
