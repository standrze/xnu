/* SPDX-License-Identifier: BSD-2-Clause */
#include "reservation_record_tree.h"
#include "firmware_seed_tree.h"
#include "firmware_seed.h"
#include "hash.h"
#include "display_xnu_handoff.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char *readall(const char *path,size_t *n)
{FILE *f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long s=ftell(f);assert(s>0);rewind(f);unsigned char *p=malloc((size_t)s);assert(p);assert(fread(p,1,(size_t)s,f)==(size_t)s);assert(!fclose(f));*n=(size_t)s;return p;}
static struct rpi5_reservation_record_tree store;
static struct rpi5_handoff_input input;
static struct rpi5_handoff_plan handoff;
static struct rpi5_resolved_reservations resolved;
static struct rpi5_range loader={0x9000000,0xa400000};
static unsigned char *fdt;static size_t bytes;
static unsigned consume_calls,finalize_calls,fail_consume,fail_finalize;
static uint8_t *selected_seed;
extern int actual_display_prefix(struct rpi5_board_tree *,struct rpi5_display_xnu_tree *,
    struct rpi5_reservation_record_tree *,const struct rpi5_display_xnu_record *);
static int consume(uint8_t *s,size_t n,uint8_t *out,size_t no,uint8_t *done)
{assert(s==selected_seed&&n==64&&no==256&&!*done);consume_calls++;*done=1;memset(s,0,64);memset(out,0x5a,no);return fail_consume?-1:0;}
int rpi5_reservation_record_finalize(struct rpi5_board_tree *tree)
{
    finalize_calls++;assert(consume_calls);for(unsigned i=0;i<64;i++)assert(!selected_seed[i]);
    if(fail_finalize)return -1;
    struct rpi5_reservation_record r;
    assert(!rpi5_reservation_record_make(fdt,bytes,0xb000000,loader,&resolved,&input,&handoff,123,&r));
    return rpi5_reservation_record_tree_commit(tree,&r,&store);
}
int main(int argc,char **argv)
{
    assert(argc==5);size_t image_bytes,missing_bytes,pinned_bytes;
    fdt=readall(argv[1],&bytes);unsigned char *image=readall(argv[2],&image_bytes);
    unsigned char *missing=readall(argv[3],&missing_bytes),*pinned=readall(argv[4],&pinned_bytes);
    struct rpi5_fdt_memory ram;struct rpi5_reservation_plan plan;
    /* Genuine pinned source DTB is parsed separately: it is not today's raw
     * firmware tree and lacks the selected seed/actual boot geometry. */
    assert(!rpi5_fdt_memory(pinned,pinned_bytes,&ram));
    /* This source DTB's unpatched CMA size has one cell where its container
     * requires two. Reject it rather than inventing today's firmware fixup. */
    assert(rpi5_reservation_record_source(pinned,pinned_bytes,&ram,&plan)==-1);
    assert(!rpi5_reservation_record_source(fdt,bytes,&ram,&plan));
    struct rpi5_range live[]={loader,{0xb000000,0xb000000+bytes}};
    assert(!rpi5_resolve_reservations(&ram,&plan,live,2,&resolved));
    assert(resolved.count==1&&resolved.allocation[0].start==0x80000&&resolved.allocation[0].end==0x4080000);
    struct rpi5_board_tree tree;const uint64_t cpu[]={0};
    assert(!rpi5_board_tree_init(cpu,1,0,54000000,(struct rpi5_range){0x107d001000,0x107d001200},0,0x200000000,&tree));
    struct rpi5_adt_property original[4];
    assert(tree.chosen.property_count==2);original[0]=tree.chosen.properties[0];original[1]=tree.chosen.properties[1];
    static const char names[][20]={"firmware-fdt","test-prefix"};
    static const uint8_t values[3]={1,2,3};
    for(unsigned i=0;i<2;i++)original[i+2]=(struct rpi5_adt_property){names[i],values+i,1};
    tree.chosen.properties=original;tree.chosen.property_count=4;
    struct rpi5_display_xnu_tree display_tree;
    assert(!rpi5_display_xnu_tree_reserve(&tree,&display_tree));
    assert(!rpi5_reservation_record_tree_reserve(&tree,&store));
    assert(rpi5_reservation_record_tree_reserve(&tree,&store)==-1);
    size_t measured;assert(!rpi5_seed_tree_measure(&tree.root,16384,&measured));
    struct rpi5_macho_placement placement;assert(!rpi5_macho_placement(image,image_bytes,0x7004000,0x6000000,0x10000000,&placement));
    uint64_t args=(placement.end+16383)&~UINT64_C(16383);
    input=(struct rpi5_handoff_input){.header_pa=0x7004000,.phys_base=0x6000000,.mem_size=0xa000000,
        .mem_actual=0x200000000,.args_pa=args,.tree_pa=args+16384};
    struct rpi5_memory_types types={0};types.normal.count=1;types.normal.extent[0]=(struct rpi5_range){0x6000000,0x10000000};
    assert(!rpi5_resolved_tree_handoff(image,image_bytes,&input,&resolved,&types,&tree.root,16384,live,2,"serial=3",8,&handoff));
    input.tree_length=(uint32_t)measured;
    struct rpi5_display_xnu_record display={.base=0x3f400000,.bytes=8294400,.reserve_start=0x3f400000,.reserve_end=0x3fbec000,
        .width=1920,.height=1080,.stride=7680,.depth=32,.alpha=2,.managed_start=0x6000000,.managed_end=0x10000000,
        .loader_start=loader.start,.loader_end=loader.end,.top=handoff.top,.fdt=0xb000000,.fdt_bytes=bytes,.owner_counter=123,.fresh_low_ram_end=0x3f400000};
    assert(actual_display_prefix(&tree,&display_tree,&store,&display)==1);
    assert(tree.chosen.properties==store.properties&&tree.chosen.property_count==6);
    struct rpi5_display_xnu_record parsed_display;
    assert(!rpi5_display_xnu_record_decode(tree.chosen.properties[4].data,tree.chosen.properties[4].length,&parsed_display));
    assert(!memcmp(&display,&parsed_display,sizeof display));
    assert(actual_display_prefix(&tree,&display_tree,&store,&display)==0); /* Original commit refuses repeat. */
    struct rpi5_reservation_record r,prior;memset(&prior,0xa5,sizeof prior);r=prior;
    struct rpi5_fdt_property seed;assert(!rpi5_firmware_seed_select(fdt,bytes,&seed));selected_seed=fdt+seed.offset;
    memset(selected_seed,0x71,64);
    assert(rpi5_reservation_record_make(fdt,bytes,0xb000000,loader,&resolved,&input,&handoff,123,&r)==-1);
    assert(!memcmp(&r,&prior,sizeof r)); /* No pre-erasure digest/output. */
    uint8_t encoded[16384];memset(encoded,0xa5,sizeof encoded);uint8_t consumed=0;size_t written=999;
    assert(!rpi5_firmware_seed_tree(&tree,selected_seed,&consumed,encoded,sizeof encoded,&written,consume));
    assert(consumed==1&&consume_calls==1&&finalize_calls==1&&written==measured);
    assert(!rpi5_reservation_record_decode(store.record,sizeof store.record,&r));
    assert(!rpi5_reservation_record_validate_fdt(&r,fdt,bytes));
    uint8_t digest[32];assert(!rpi5_sha256(fdt,bytes,digest));assert(!memcmp(digest,r.fdt_sha256,32));
    assert(r.tree_bytes==measured&&r.dynamic_count==1&&r.fixed_count==1);
    assert(rpi5_reservation_record_tree_commit(&tree,&r,&store)==-1); /* No second commit. */
    uint8_t raw[1057];assert(!rpi5_reservation_record_encode(&r,raw,1056));
    struct rpi5_reservation_record decoded;assert(!rpi5_reservation_record_decode(raw,1056,&decoded));
    assert(!memcmp(&r,&decoded,sizeof r));
    for(unsigned n=0;n<1056;n++){decoded=prior;assert(rpi5_reservation_record_decode(raw,n,&decoded)==-1);assert(!memcmp(&decoded,&prior,sizeof decoded));}
    assert(rpi5_reservation_record_decode(raw,1057,&decoded)==-1);
    for(unsigned word=0;word<24;word++){
        if(word==19)continue; /* Counter is live context, not authentication. */
        uint8_t corrupt[1056];memcpy(corrupt,raw,sizeof corrupt);memset(corrupt+8*word,0xff,8);decoded=prior;
        assert(rpi5_reservation_record_decode(corrupt,sizeof corrupt,&decoded)==-1);assert(!memcmp(&decoded,&prior,sizeof decoded));
    }
    union {struct rpi5_reservation_record value;uint8_t raw[1056];} alias;
    alias.value=r;assert(rpi5_reservation_record_encode(&alias.value,alias.raw,1056)==-1);
    memcpy(alias.raw,raw,1056);assert(rpi5_reservation_record_decode(alias.raw,1056,&alias.value)==-1);
    struct rpi5_reservation_record bad=r;
    bad.dynamic_count=0;memset(bad.dynamic,0,sizeof bad.dynamic);
    assert(!rpi5_reservation_record_valid(&bad));assert(rpi5_reservation_record_validate_fdt(&bad,fdt,bytes)==-1);
    bad=r;bad.fixed_count=0;memset(bad.fixed,0,sizeof bad.fixed);
    assert(!rpi5_reservation_record_valid(&bad));assert(rpi5_reservation_record_validate_fdt(&bad,fdt,bytes)==-1);
    bad=r;bad.dynamic[0].node_offset++;assert(rpi5_reservation_record_validate_fdt(&bad,fdt,bytes)==-1);
    bad=r;bad.dynamic[0].start+=0x10000;bad.dynamic[0].end+=0x10000;
    assert(!rpi5_reservation_record_valid(&bad));assert(rpi5_reservation_record_validate_fdt(&bad,fdt,bytes)==-1); /* Same-window different claim. */
    bad=r;bad.dynamic[0].start=0x6000000;bad.dynamic[0].end=0xa000000;
    assert(rpi5_reservation_record_valid(&bad)==-1); /* No managed overlap. */
    bad=r;bad.fixed[bad.fixed_count]=(struct rpi5_range){1,2};assert(rpi5_reservation_record_valid(&bad)==-1);
    bad=r;bad.dynamic[1]=bad.dynamic[0];assert(rpi5_reservation_record_valid(&bad)==-1);
    assert(rpi5_reservation_record_validate_fdt(&r,missing,missing_bytes)==-1);
    struct rpi5_resolved_reservations dirty=resolved;dirty.available.extent[0].start++;
    decoded=prior;assert(rpi5_reservation_record_make(fdt,bytes,0xb000000,loader,&dirty,&input,&handoff,123,&decoded)==-1);
    assert(!memcmp(&decoded,&prior,sizeof decoded));
    struct rpi5_handoff_plan wrong=handoff;wrong.args[104]^=1;
    assert(rpi5_reservation_record_make(fdt,bytes,0xb000000,loader,&resolved,&input,&wrong,123,&decoded)==-1);
    /* Exact post-consume hook: failure never encodes/publishes and cannot
     * silently skip finalization. Native consume is an isolated boundary spy. */
    for(unsigned mode=0;mode<2;mode++){
        memset(store.record,0,sizeof store.record);memset(selected_seed,0x71,64);consumed=0;written=999;
        consume_calls=finalize_calls=0;fail_consume=mode==0;fail_finalize=mode==1;
        assert(rpi5_firmware_seed_tree(&tree,selected_seed,&consumed,encoded,sizeof encoded,&written,consume)==-1);
        assert(consumed==1&&consume_calls==1&&finalize_calls==(mode==1)&&written==999);
        for(unsigned i=0;i<1056;i++)assert(!store.record[i]);
    }
    free(pinned);free(missing);free(image);free(fdt);
    puts("RESERVATION_RECORD_PASS REAL_PLANNER_CODEC_SHA SEED_ERASE_BEFORE_DIGEST MANAGED_UNCHANGED NO_HARDWARE");
}
