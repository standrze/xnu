/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_allocation_retained.h"
static int overlap(struct rpi5_range a,struct rpi5_range b)
{return a.start<b.end&&b.start<a.end;}
static int range(struct rpi5_range r)
{return r.start<r.end&&r.end<=(UINT64_C(1)<<40);}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&!(x<y+nb&&y<x+na);}
int rpi5_display_allocation_retained(const struct rpi5_display_allocate_result *result,
    const struct rpi5_display_allocate_report *report,const void *fdt,size_t bytes,
    uint64_t fdt_pa,struct rpi5_range image,const struct rpi5_range *extra,size_t count,
    struct rpi5_display_retained *out)
{
    if(!result||!report||!fdt||!out||bytes<40||bytes>1048576||count>64||(count&&!extra)||
        !apart(out,sizeof *out,result,sizeof *result)||!apart(out,sizeof *out,report,sizeof *report)||
        !apart(out,sizeof *out,fdt,bytes)||(count&&!apart(out,sizeof *out,extra,count*sizeof *extra))||
        !range(image)||fdt_pa<0x80000||(fdt_pa&7)||fdt_pa>UINT32_MAX||bytes>UINT64_C(0x100000000)-fdt_pa||
        report->result||report->admission!=1||report->candidate_valid!=1||report->decoded_replies!=15||
        report->session.state!=RPI5_DISPLAY_MBOX_COMPLETE||report->session.completed!=15||
        report->session.tx_attempted!=15||report->session.pop_attempted!=15||report->session.quarantined_buffers||
        report->session.stage!=12||report->session.slot!=3||report->session.busy||report->session.error||
        report->session.polls>512||report->session.callbacks>4096||
        report->session.start_us>report->session.last_us||report->session.last_us>=report->session.deadline_us||
        report->session.deadline_us-report->session.start_us!=1000000||report->mmio_writes!=4||report->cache_operations!=12)return -1;
    static const unsigned lengths[]={17,1,16,30};
    for(unsigned s=0;s<4;s++){
        if(result->reply[s].count!=lengths[s]||report->replies[s].count!=lengths[s])return -1;
        for(unsigned i=0;i<lengths[s];i++)if(result->reply[s].words[i]!=report->replies[s].words[i])return -1;
    }
    const uint32_t *a=result->reply[2].words,*b=result->reply[3].words;
    static const uint32_t wanted[]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0};
    static const uint32_t preflight[]={1,0,1920,1080,32,7680,1920,1080,0,0,0,0,0,0,0,0,0};
    static const uint32_t raw_settings[]={0,1920,1080,32,7680,1920,1080,0,0,0,0,0,0,0,0,0};
    for(unsigned i=0;i<13;i++)if(a[i]!=wanted[i]||b[i]!=wanted[i])return -1;
    for(unsigned i=0;i<17;i++)if(result->reply[0].words[i]!=preflight[i])return -1;
    for(unsigned i=0;i<16;i++)if(b[i+14]!=raw_settings[i])return -1;
    if(result->reply[1].words[0]||a[15]!=7680||b[13]!=7680)return -1;
    uint64_t base=a[13],size=a[14],end=base+size,rounded=(end+16383)&~UINT64_C(16383);
    if((base&UINT64_C(0xc0000000))||!base||(base&16383)||size<8294400||size>16*1024*1024||end<=base||rounded<end||rounded>0x40000000)return -1;
    const struct rpi5_display_allocate_candidate *c=&report->candidate;
    if(c->bus_address!=base||c->cpu_address!=base||c->allocation_bytes!=size||c->reservation_start!=base||
        c->reservation_end!=rounded||c->width!=1920||c->height!=1080||c->stride!=7680||c->depth!=32||c->pixel_order||c->alpha_mode!=2)return -1;
    struct rpi5_display_retained retained={.framebuffer={{base,end},8294400,1920,1080,7680,RPI5_FB_XRGB8888},.retained_pages={base,rounded}};
    struct rpi5_fdt_memory ram;struct rpi5_reservation_plan plan;
    if(rpi5_fdt_memory(fdt,bytes,&ram)||rpi5_fdt_reservation_plan(fdt,bytes,&plan))return -1;
    for(unsigned i=0;i<ram.count;i++){
        if(!ram.start[i]){if(retained.fresh_low_ram_end)return -1;retained.fresh_low_ram_end=ram.end[i];}
        if(overlap(retained.retained_pages,(struct rpi5_range){ram.start[i],ram.end[i]}))return -1;
    }
    if(retained.fresh_low_ram_end<0x3e000000||retained.fresh_low_ram_end>0x3fc00000||base<retained.fresh_low_ram_end)return -1;
    struct rpi5_range original={fdt_pa,fdt_pa+bytes},secure={fdt_pa&~UINT64_C(0x1fffff),(fdt_pa&~UINT64_C(0x1fffff))+0x400000};
    if(overlap(retained.retained_pages,image)||overlap(retained.retained_pages,original)||overlap(retained.retained_pages,secure))return -1;
    for(size_t i=0;i<plan.fixed.count;i++)if(overlap(retained.retained_pages,plan.fixed.extent[i]))return -1;
    struct rpi5_range initrd;int ir=rpi5_fdt_initrd(fdt,bytes,&initrd);
    if(ir!=1&&(ir||overlap(retained.retained_pages,initrd)))return -1;
    for(size_t i=0;i<count;i++)if(!range(extra[i])||overlap(retained.retained_pages,extra[i]))return -1;
    *out=retained;return 0;
}
