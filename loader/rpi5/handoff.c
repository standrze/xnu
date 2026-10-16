/* SPDX-License-Identifier: BSD-2-Clause */
#include "handoff.h"
int rpi5_handoff_plan(const void *image, size_t size, const struct rpi5_handoff_input *input,
    const struct rpi5_range *live, size_t live_count, const char *command,
    size_t command_length, struct rpi5_handoff_plan *out)
{
    const uint64_t limit=1ull<<40, link=0xfffffe0007004000ull;
    if (!input || !out || !live || !live_count || live_count>24) return -1;
    struct rpi5_handoff_input a=*input;
    if (!a.mem_size || a.mem_size>a.mem_actual || a.mem_actual>limit ||
        a.phys_base>=limit || a.mem_size>limit-a.phys_base || a.header_pa<a.phys_base ||
        a.header_pa-a.phys_base>link || (a.args_pa&7) || a.args_pa>limit-RPI5_BOOT_ARGS_SIZE ||
        !a.tree_length || a.tree_pa>=limit || a.tree_length>limit-a.tree_pa) return -1;
    struct rpi5_handoff_plan result={0};
    if (rpi5_macho_placement(image,size,a.header_pa,a.usable.start,a.usable.end,&result.kernel) ||
        a.args_pa<result.kernel.end || a.tree_pa<result.kernel.end) return -1;
    struct rpi5_range required[28];
    required[0]=(struct rpi5_range){a.header_pa,result.kernel.end};
    required[1]=(struct rpi5_range){a.args_pa,a.args_pa+RPI5_BOOT_ARGS_SIZE};
    required[2]=(struct rpi5_range){a.tree_pa,a.tree_pa+a.tree_length};
    size_t count=3+live_count;
    for (size_t i=0;i<live_count;i++) required[3+i]=live[i];
    if (rpi5_ranges_validate_live(&a.usable,1,required,count)) return -1;
    uint64_t top=0;
    for (size_t i=0;i<count;i++) if (required[i].end>top) top=required[i].end;
    top=(top+0x3fff)&~0x3fffull;
    required[count++]=(struct rpi5_range){top-1,top};
    uint64_t virt=link-(a.header_pa-a.phys_base);
    if (rpi5_bootstrap_mapping(a.phys_base,virt,a.mem_size,a.header_pa,a.usable,
        required,count,&result.mapping)) return -1;
    struct rpi5_boot_args_input args={virt,a.phys_base,a.mem_size,top,a.tree_pa,
        result.kernel.end,a.mem_actual,a.tree_length};
    if (rpi5_boot_args_encode(&args,command,command_length,result.args,sizeof(result.args))) return -1;
    result.top=top;
    result.args_pa=a.args_pa;
    *out=result;
    return 0;
}
