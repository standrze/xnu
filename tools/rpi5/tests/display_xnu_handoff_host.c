/* SPDX-License-Identifier: BSD-2-Clause */
/* Pure ownership/ABI/policy validation; no mapping, framebuffer or Pi access. */
#include "display_xnu_handoff.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    struct rpi5_display_retained retained={.framebuffer={{0x3f400000,0x3fbe9000},8294400,1920,1080,7680,RPI5_FB_XRGB8888},
        .retained_pages={0x3f400000,0x3fbec000},.fresh_low_ram_end=0x3f400000};
    struct rpi5_memory_types old={.normal={{{0,0x3f400000},{0x40000000,0x200000000}},2},
        .device={{{0x107d000000,0x107d004000}},1}},before=old,typed;
    assert(!rpi5_display_xnu_types(&retained,&old,&typed));assert(!memcmp(&old,&before,sizeof old));
    assert(typed.normal.count==3&&typed.normal.extent[0].end==0x3f400000&&typed.normal.extent[1].start==0x3f400000&&typed.normal.extent[1].end==0x3fbec000);
    assert(rpi5_memory_type_for(&typed,(struct rpi5_range){0x3f400000,0x3fbec000})==RPI5_MEMORY_NORMAL);
    assert(rpi5_memory_type_for(&typed,(struct rpi5_range){0x3fbec000,0x40000000})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&typed,(struct rpi5_range){0x6000000,0x10000000})==RPI5_MEMORY_NORMAL);
    assert(rpi5_display_xnu_types(&retained,&old,&old));assert(rpi5_display_xnu_types(&retained,&typed,&before));
    struct rpi5_display_allocate_report allocation={.result=0,.admission=1,.candidate_valid=1,.counter_start=73,
        .session={.state=RPI5_DISPLAY_MBOX_COMPLETE,.completed=15},
        .candidate={.cpu_address=0x3f400000,.allocation_bytes=8294400,.reservation_start=0x3f400000,.reservation_end=0x3fbec000}};
    struct rpi5_handoff_input input={.phys_base=0x6000000,.mem_size=0xa000000,.tree_pa=0x8004000,.tree_length=4096,.args_pa=0x8000000};
    struct rpi5_handoff_plan base={.kernel={.end=0x8000000},.mapping={.physical_start=0x6000000,.physical_end=0x10000000},.args_pa=0x8000000,.top=0xb018000},out,before_out;
    struct rpi5_boot_args_input args={0xfffffe0006000000,0x6000000,0xa000000,base.top,input.tree_pa,base.kernel.end,0x200000000,4096};
    assert(!rpi5_boot_args_encode(&args,"serial=3",8,base.args,sizeof base.args));
    struct rpi5_display_xnu_record record,decoded;
    assert(!rpi5_display_xnu_handoff(&retained,&allocation,0xb000000,0x13a32,(struct rpi5_range){0x9000000,0xa800000},&input,&base,&out,&record));
    for(unsigned i=0;i<sizeof base.args;i++)if(i<40||i>=88)assert(out.args[i]==base.args[i]);
    assert(rpi5_display_xnu_le(out.args+40)==0x3f400001&&rpi5_display_xnu_le(out.args+48)==0&&rpi5_display_xnu_le(out.args+56)==7680);
    assert(rpi5_display_xnu_le(out.args+64)==1920&&rpi5_display_xnu_le(out.args+72)==1080&&rpi5_display_xnu_le(out.args+80)==32);
    assert(out.top==base.top&&out.mapping.physical_start==base.mapping.physical_start&&out.mapping.physical_end==base.mapping.physical_end);
    uint8_t encoded[192],scratch[192];assert(!rpi5_display_xnu_record_encode(&record,encoded,sizeof encoded));
    assert(!rpi5_display_xnu_record_decode(encoded,sizeof encoded,&decoded));assert(!memcmp(&record,&decoded,sizeof record));
    assert(!rpi5_display_xnu_video_valid(&record,0x3f400001,1920,1080,7680,32,0,0,0,1));
    assert(rpi5_display_xnu_video_valid(&record,0x3f400000,1920,1080,7680,32,0,0,0,1));
    assert(rpi5_display_xnu_video_valid(&record,0x3f400001,1920,1080,7680,32,4,0,0,1));
    assert(rpi5_display_xnu_video_valid(&record,0x3f400001,1920,1080,7680,32,0,8294400,0,1));
    for(unsigned n=0;n<24;n++){
        memcpy(scratch,encoded,sizeof scratch);scratch[n*8]^=0x80;
        if(n==15||n==17||n==18||n==19)continue; /* Bounded dynamic lineage fields, not signatures. */
        struct rpi5_display_xnu_record prior=decoded;
        assert(rpi5_display_xnu_record_decode(scratch,sizeof scratch,&decoded));assert(!memcmp(&decoded,&prior,sizeof decoded));
    }
    assert(rpi5_display_xnu_map_policy(&record,0x3f400000,0x3fbec000,1,1,1)==1);
    assert(rpi5_display_xnu_map_policy(&record,0x3f400000,0x3f404000,1,1,0)==1);
    assert(rpi5_display_xnu_map_policy(&record,0x6000000,0x10000000,0,0,1)==0);
    assert(rpi5_display_xnu_map_policy(&record,0x3f400000,0x3fbec000,0,1,1)==-1);
    assert(rpi5_display_xnu_map_policy(&record,0x3f400000,0x3fbec000,1,0,1)==-1);
    assert(rpi5_display_xnu_map_policy(&record,0x3f400000,0x3f404000,1,1,1)==-1);
    assert(rpi5_display_xnu_map_policy(&record,0x3f3fc000,0x3fbec000,1,1,0)==-1);
    assert(rpi5_display_xnu_map_policy(&record,0x3f400001,0x3fbec000,1,1,0)==-1);
    memset(&before_out,0xa5,sizeof before_out);out=before_out;
    struct rpi5_handoff_input changed=input;changed.mem_size+=16384;
    assert(rpi5_display_xnu_handoff(&retained,&allocation,0xb000000,0x13a32,(struct rpi5_range){0x9000000,0xa800000},&changed,&base,&out,&record));
    assert(!memcmp(&out,&before_out,sizeof out));
    struct rpi5_adt_property original_properties[4]={{"dram-base",0,8},{"dram-size",0,8},
        {"rpi5-memory-map",0,128},{"rpi5-firmware-fdt",0,64}};
    struct rpi5_board_tree tree={.chosen={.properties=original_properties,.property_count=4}};
    struct rpi5_display_xnu_tree storage;
    assert(!rpi5_display_xnu_tree_reserve(&tree,&storage));
    assert(tree.chosen.property_count==5&&tree.chosen.properties==storage.properties);
    for(unsigned i=0;i<4;i++)assert(!memcmp(&original_properties[i],&storage.properties[i],sizeof original_properties[i]));
    assert(rpi5_display_xnu_record_decode(storage.record,sizeof storage.record,&decoded));
    assert(!rpi5_display_xnu_tree_commit(&tree,&record,&storage));
    assert(!rpi5_display_xnu_record_decode(storage.record,sizeof storage.record,&decoded));
    assert(rpi5_display_xnu_tree_commit(&tree,&record,&storage)); /* One commit only. */
    assert(rpi5_display_xnu_tree_reserve(&tree,&storage));
    struct rpi5_display_xnu_record bad=record;
    bad.fdt=bad.loader_end-8;assert(rpi5_display_xnu_record_valid(&bad));
    bad=record;bad.fdt_bytes=bad.top-bad.fdt+1;assert(rpi5_display_xnu_record_valid(&bad));
    bad=record;bad.loader_end=bad.top+1;assert(rpi5_display_xnu_record_valid(&bad));
    bad=record;bad.owner_counter=0;assert(rpi5_display_xnu_record_valid(&bad));
    puts("DISPLAY_XNU HANDOFF PASS EXACT_RETAINED_SIX_VIDEO_FIELDS MANAGED_UNCHANGED NO_WB_POLICY NO_MAPPING_OR_HARDWARE");return 0;
}
