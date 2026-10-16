/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_xnu_handoff.h"
static int overlap(struct rpi5_range a,struct rpi5_range b)
{return a.start<b.end&&b.start<a.end;}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&!(x<y+nb&&y<x+na);}
int rpi5_display_xnu_types(const struct rpi5_display_retained *r,
    const struct rpi5_memory_types *input,struct rpi5_memory_types *out)
{
    if(!r||!input||!out||input==out||rpi5_memory_types_validate(input)||input->normal.count>=32||
        r->retained_pages.start!=r->framebuffer.allocation.start||
        r->retained_pages.end!=((r->framebuffer.allocation.end+16383)&~UINT64_C(16383))||
        r->retained_pages.start<0x3e000000||r->retained_pages.end>0x40000000||
        r->retained_pages.start>=r->retained_pages.end||((r->retained_pages.start|r->retained_pages.end)&16383))return -1;
    struct rpi5_memory_types result=*input;size_t position=0;
    for(size_t i=0;i<result.normal.count;i++){
        if(overlap(result.normal.extent[i],r->retained_pages))return -1;
        if(result.normal.extent[i].start<r->retained_pages.start)position++;
    }
    for(size_t i=0;i<result.device.count;i++)if(overlap(result.device.extent[i],r->retained_pages))return -1;
    for(size_t i=result.normal.count;i>position;i--)result.normal.extent[i]=result.normal.extent[i-1];
    result.normal.extent[position]=r->retained_pages;result.normal.count++;
    if(rpi5_memory_types_validate(&result))return -1;
    *out=result;return 0;
}
static void put64(uint8_t *p,uint64_t n)
{for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(n>>(8*i));}
int rpi5_display_xnu_handoff(const struct rpi5_display_retained *r,
    const struct rpi5_display_allocate_report *allocation,uint64_t fdt,size_t bytes,
    struct rpi5_range loader,const struct rpi5_handoff_input *input,
    const struct rpi5_handoff_plan *restrict base,struct rpi5_handoff_plan *restrict out,
    struct rpi5_display_xnu_record *record)
{
    if(!r||!allocation||!input||!base||!out||!record||
        !apart(base,sizeof *base,out,sizeof *out)||!apart(out,sizeof *out,record,sizeof *record)||
        !apart(out,sizeof *out,r,sizeof *r)||!apart(out,sizeof *out,allocation,sizeof *allocation)||
        !apart(out,sizeof *out,input,sizeof *input)||!apart(record,sizeof *record,base,sizeof *base)||
        !apart(record,sizeof *record,r,sizeof *r)||!apart(record,sizeof *record,allocation,sizeof *allocation)||
        !apart(record,sizeof *record,input,sizeof *input)||allocation->result||
        allocation->candidate_valid!=1||allocation->session.completed!=15||allocation->session.quarantined_buffers||
        allocation->session.state!=RPI5_DISPLAY_MBOX_COMPLETE||!allocation->counter_start||
        input->phys_base!=0x6000000||input->mem_size!=0xa000000||
        base->mapping.physical_start<input->phys_base||base->mapping.physical_end>input->phys_base+input->mem_size||
        base->args_pa!=input->args_pa||loader.start<base->kernel.end||
        base->top<input->tree_pa||input->tree_length>base->top-input->tree_pa||
        r->framebuffer.allocation.start!=allocation->candidate.cpu_address||
        r->framebuffer.allocation.end-r->framebuffer.allocation.start!=allocation->candidate.allocation_bytes||
        r->retained_pages.start!=allocation->candidate.reservation_start||r->retained_pages.end!=allocation->candidate.reservation_end)return -1;
    struct rpi5_display_xnu_record value={r->framebuffer.allocation.start,
        r->framebuffer.allocation.end-r->framebuffer.allocation.start,r->retained_pages.start,r->retained_pages.end,
        r->framebuffer.width,r->framebuffer.height,r->framebuffer.stride,32,0,2,input->phys_base,input->phys_base+input->mem_size,
        loader.start,loader.end,base->top,fdt,bytes,allocation->counter_start,r->fresh_low_ram_end};
    if(rpi5_display_xnu_record_valid(&value)||r->framebuffer.format!=RPI5_FB_XRGB8888||r->framebuffer.visible_bytes!=8294400||
        overlap(r->retained_pages,(struct rpi5_range){input->phys_base,input->phys_base+input->mem_size}))return -1;
    /* Bind to the real previously checked headless boot_args, not a second
     * independently serialized command or guessed structure layout. */
    if(rpi5_display_xnu_le(base->args+16)!=input->phys_base||rpi5_display_xnu_le(base->args+24)!=input->mem_size||
        rpi5_display_xnu_le(base->args+32)!=base->top)return -1;
    for(unsigned i=40;i<88;i++)if(base->args[i])return -1;
    struct rpi5_handoff_plan result=*base;
    put64(result.args+40,value.base|1);put64(result.args+48,0);put64(result.args+56,7680);
    put64(result.args+64,1920);put64(result.args+72,1080);put64(result.args+80,32);
    *out=result;*record=value;return 0;
}
static int equal(const char *a,const char *b)
{while(*a&&*a==*b){a++;b++;}return *a==*b;}
int rpi5_display_xnu_tree_attach(struct rpi5_board_tree *tree,const struct rpi5_display_xnu_record *r,
    struct rpi5_display_xnu_tree *storage)
{
    if(rpi5_display_xnu_record_valid(r))return -1;
    if(rpi5_display_xnu_tree_reserve(tree,storage))return -1;
    return rpi5_display_xnu_tree_commit(tree,r,storage);
}
int rpi5_display_xnu_tree_reserve(struct rpi5_board_tree *tree,struct rpi5_display_xnu_tree *storage)
{
    if(!tree||!storage||!tree->chosen.properties||tree->chosen.property_count!=4||
        !apart(tree,sizeof *tree,storage,sizeof *storage)||
        !apart(tree->chosen.properties,4*sizeof *tree->chosen.properties,storage,sizeof *storage))return -1;
    for(unsigned i=0;i<4;i++)if(equal(tree->chosen.properties[i].name,"rpi5-framebuffer"))return -1;
    for(unsigned i=0;i<sizeof storage->record;i++)storage->record[i]=0;
    for(unsigned i=0;i<4;i++)storage->properties[i]=tree->chosen.properties[i];
    storage->properties[4]=(struct rpi5_adt_property){"rpi5-framebuffer",storage->record,sizeof storage->record};
    tree->chosen.properties=storage->properties;tree->chosen.property_count=5;return 0;
}
int rpi5_display_xnu_tree_commit(struct rpi5_board_tree *tree,const struct rpi5_display_xnu_record *r,
    struct rpi5_display_xnu_tree *storage)
{
    if(!tree||!storage||tree->chosen.property_count!=5||tree->chosen.properties!=storage->properties||
        !equal(storage->properties[4].name,"rpi5-framebuffer")||storage->properties[4].data!=storage->record||
        storage->properties[4].length!=sizeof storage->record||rpi5_display_xnu_record_valid(r))return -1;
    for(unsigned i=0;i<sizeof storage->record;i++)if(storage->record[i])return -1;
    uint8_t encoded[RPI5_DISPLAY_XNU_RECORD_BYTES];
    if(rpi5_display_xnu_record_encode(r,encoded,sizeof encoded))return -1;
    for(unsigned i=0;i<sizeof encoded;i++)storage->record[i]=encoded[i];
    return 0;
}
