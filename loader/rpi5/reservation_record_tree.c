/* SPDX-License-Identifier: BSD-2-Clause */
#include "reservation_record_tree.h"
#include "bearssl_hash.h"
#include "firmware_fdt_record.h"
#include "firmware_seed.h"
static int equal(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int views(const struct rpi5_ranges *a,const struct rpi5_ranges *b)
{if(a->count!=b->count||a->count>32)return 0;for(size_t i=0;i<a->count;i++)if(a->extent[i].start!=b->extent[i].start||a->extent[i].end!=b->extent[i].end)return 0;return 1;}
int rpi5_reservation_record_tree_reserve(struct rpi5_board_tree *tree,struct rpi5_reservation_record_tree *s)
{
    if(!tree||!s||!tree->chosen.properties||tree->chosen.property_count!=5)return -1;
    for(unsigned i=0;i<5;i++)if(equal(tree->chosen.properties[i].name,RPI5_RESERVATION_RECORD_PROPERTY))return -1;
    for(unsigned i=0;i<sizeof s->record;i++)s->record[i]=0;
    for(unsigned i=0;i<5;i++)s->properties[i]=tree->chosen.properties[i];
    s->properties[5]=(struct rpi5_adt_property){RPI5_RESERVATION_RECORD_PROPERTY,s->record,sizeof s->record};
    tree->chosen.properties=s->properties;tree->chosen.property_count=6;return 0;
}
int rpi5_reservation_record_make(const void *fdt,size_t bytes,uint64_t pa,struct rpi5_range loader,
    const struct rpi5_resolved_reservations *actual,const struct rpi5_handoff_input *input,
    const struct rpi5_handoff_plan *handoff,uint64_t counter,struct rpi5_reservation_record *out)
{
    if(!actual||!input||!handoff||!out||bytes>UINT64_MAX-pa||
        input->mem_size>UINT64_MAX-input->phys_base||handoff->args_pa!=input->args_pa)return -1;
    struct rpi5_fdt_memory ram;struct rpi5_reservation_plan p;struct rpi5_resolved_reservations resolved;
    struct rpi5_range live[]={loader,{pa,pa+bytes}};
    if(rpi5_reservation_record_source(fdt,bytes,&ram,&p)||rpi5_resolve_reservations(&ram,&p,live,2,&resolved)||
        actual->count!=resolved.count||actual->count>8||!views(&actual->available,&resolved.available)||
        !views(&actual->reservation_free,&resolved.reservation_free))return -1;
    for(unsigned i=0;i<actual->count;i++)if(actual->allocation[i].start!=resolved.allocation[i].start||
        actual->allocation[i].end!=resolved.allocation[i].end)return -1;
    struct rpi5_reservation_record r={0};struct rpi5_ranges fixed;
    if(rpi5_reservation_record_fixed(&p,&fixed))return -1;
    r.fixed_count=fixed.count;r.dynamic_count=p.count;
    r.managed_start=input->phys_base;r.managed_end=input->phys_base+input->mem_size;
    r.loader_start=loader.start;r.loader_end=loader.end;r.fdt_pa=pa;r.fdt_bytes=bytes;
    r.args_pa=input->args_pa;r.args_bytes=RPI5_BOOT_ARGS_SIZE;r.tree_pa=input->tree_pa;r.tree_bytes=input->tree_length;
    r.top=handoff->top;r.kernel_start=handoff->kernel.header;r.kernel_end=handoff->kernel.end;r.owner_counter=counter;
    /* Public maker itself enforces post-consumption ordering. Never hash even
     * transiently while the selected firmware random seed is still live. */
    struct rpi5_fdt_property seed;
    if(rpi5_firmware_seed_select(fdt,bytes,&seed))return -1;
    for(unsigned i=0;i<64;i++)if(((const uint8_t *)fdt)[seed.offset+i])return -1;
    /* Same genuine loader BearSSL implementation, without hash_progress:
     * that unrelated payload callback may print or service a PM watchdog. */
    br_sha256_context digest;
    br_sha256_init(&digest);
    br_sha256_update(&digest,fdt,bytes);
    br_sha256_out(&digest,r.fdt_sha256);
    for(size_t i=0;i<fixed.count;i++)r.fixed[i]=fixed.extent[i];
    for(unsigned i=0;i<p.count;i++)r.dynamic[i]=(struct rpi5_reservation_claim){p.request[i].node_offset,
        p.request[i].no_map,resolved.allocation[i].start,resolved.allocation[i].end,p.request[i].alignment};
    if(rpi5_reservation_record_validate_fdt(&r,fdt,bytes)||
        rpi5_fdt_record_le64(handoff->args+16)!=input->phys_base||
        rpi5_fdt_record_le64(handoff->args+24)!=input->mem_size||
        rpi5_fdt_record_le64(handoff->args+32)!=handoff->top||
        rpi5_fdt_record_le64(handoff->args+96)!=rpi5_fdt_record_le64(handoff->args+8)+input->tree_pa-input->phys_base||
        ((uint32_t)handoff->args[104]|(uint32_t)handoff->args[105]<<8|
         (uint32_t)handoff->args[106]<<16|(uint32_t)handoff->args[107]<<24)!=input->tree_length)return -1;
    *out=r;return 0;
}
int rpi5_reservation_record_tree_commit(struct rpi5_board_tree *tree,const struct rpi5_reservation_record *r,
    struct rpi5_reservation_record_tree *s)
{
    if(!tree||!s||tree->chosen.property_count!=6||tree->chosen.properties!=s->properties||
        !equal(s->properties[5].name,RPI5_RESERVATION_RECORD_PROPERTY)||s->properties[5].data!=s->record||
        s->properties[5].length!=sizeof s->record)return -1;
    for(unsigned i=0;i<sizeof s->record;i++)if(s->record[i])return -1;
    return rpi5_reservation_record_encode(r,s->record,sizeof s->record);
}
