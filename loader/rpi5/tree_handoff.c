/* SPDX-License-Identifier: BSD-2-Clause */
#include "tree_handoff.h"
int rpi5_tree_handoff_plan(const void *image, size_t size,
    const struct rpi5_handoff_input *input, const struct rpi5_adt_node *tree,
    size_t tree_capacity, const struct rpi5_range *live, size_t live_count,
    const char *command, size_t command_length, struct rpi5_handoff_plan *out)
{
    if (!input || input->tree_length) return -1;
    size_t measured;
    if (rpi5_seed_tree_measure(tree,tree_capacity,&measured)) return -1;
    struct rpi5_handoff_input a=*input;
    a.tree_length=(uint32_t)measured; /* measurement is bounded to 16 MiB */
    return rpi5_handoff_plan(image,size,&a,live,live_count,command,command_length,out);
}

int rpi5_resolved_tree_handoff(const void *image, size_t size,
    const struct rpi5_handoff_input *input,
    const struct rpi5_resolved_reservations *resolved,
    const struct rpi5_memory_types *types,
    const struct rpi5_adt_node *tree, size_t tree_capacity,
    const struct rpi5_range *live, size_t live_count,
    const char *command, size_t command_length, struct rpi5_handoff_plan *out)
{
    if (!input || !resolved || !out || input->usable.start || input->usable.end ||
        !input->mem_size || input->phys_base>=(1ull<<40) ||
        input->mem_size>(1ull<<40)-input->phys_base ||
        rpi5_ranges_validate_live(resolved->reservation_free.extent,
            resolved->reservation_free.count,live,live_count)) return -1;
    if (rpi5_memory_type_for(types,(struct rpi5_range){input->phys_base,
            input->phys_base+input->mem_size})!=RPI5_MEMORY_NORMAL) return -1;
    struct rpi5_handoff_input a=*input;
    for (size_t i=0;i<resolved->reservation_free.count;i++) {
        struct rpi5_range r=resolved->reservation_free.extent[i];
        if (r.start<=a.phys_base && r.end>=a.phys_base+a.mem_size) {
            a.usable=r;
            struct rpi5_handoff_plan result;
            if (rpi5_tree_handoff_plan(image,size,&a,tree,tree_capacity,
                live,live_count,command,command_length,&result)) return -1;
            if (rpi5_memory_type_for(types,(struct rpi5_range){
                    result.mapping.physical_start,result.mapping.physical_end})
                    !=RPI5_MEMORY_NORMAL) return -1;
            *out=result;
            return 0;
        }
    }
    return -1;
}
