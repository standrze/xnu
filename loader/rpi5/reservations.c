/* SPDX-License-Identifier: BSD-2-Clause */
#include "fdt.h"
int rpi5_resolve_reservations(const struct rpi5_fdt_memory *ram,
    const struct rpi5_reservation_plan *plan, const struct rpi5_range *live,
    size_t live_count, struct rpi5_resolved_reservations *out)
{
    if (!ram || !plan || !out || !ram->count || ram->count>8 || plan->count>8 ||
        plan->fixed.count>32 || live_count>24 || (live_count && !live)) return -1;
    struct rpi5_range memory[8], excluded[64];
    size_t ne=0;
    for (size_t i=0;i<ram->count;i++) memory[i]=(struct rpi5_range){ram->start[i],ram->end[i]};
    for (size_t i=0;i<plan->fixed.count;i++) excluded[ne++]=plan->fixed.extent[i];
    for (size_t i=0;i<live_count;i++) excluded[ne++]=live[i];
    struct rpi5_resolved_reservations result={0};
    if (rpi5_ranges_subtract(memory,ram->count,excluded,ne,&result.available)) return -1;
    for (size_t i=0;i<plan->count;i++) {
        const struct rpi5_dynamic_reservation *r=&plan->request[i];
        if (!r->window_count || r->window_count>8 || r->no_map>1) return -1;
        if (rpi5_ranges_find(&result.available,r->window,r->window_count,r->size,r->alignment,&result.allocation[i])) return -1;
        excluded[ne++]=result.allocation[i];
        if (rpi5_ranges_subtract(memory,ram->count,excluded,ne,&result.available)) return -1;
        result.count++;
    }
    /* A bootstrap mapping may contain live loader buffers, whereas new writes
     * must use available. Do not reintroduce fixed or dynamic reservations. */
    ne=0;
    for (size_t i=0;i<plan->fixed.count;i++) excluded[ne++]=plan->fixed.extent[i];
    for (size_t i=0;i<result.count;i++) excluded[ne++]=result.allocation[i];
    if (rpi5_ranges_subtract(memory,ram->count,excluded,ne,&result.reservation_free)) return -1;
    *out=result; return 0;
}
