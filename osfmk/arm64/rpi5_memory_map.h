/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_KERNEL_MEMORY_MAP_H
#define RPI5_KERNEL_MEMORY_MAP_H
#include <stdint.h>
#include <stddef.h>
/* Private BCM2712 loader contract. Missing addresses are unknown (0).
 * Type is not allocation ownership; reservations are handled separately. */
struct rpi5_kernel_memory_map {
    uint64_t type[64], start[64], end[64];
    unsigned count;
};
static inline uint64_t
rpi5_map_le(const uint8_t *p, unsigned n)
{
    uint64_t v=0;
    for (unsigned i=0;i<n;i++) v|=(uint64_t)p[i]<<(8*i);
    return v;
}
/* Validate completely before publishing. Input/output must be disjoint. */
static inline int
rpi5_map_decode(const void *data, size_t length, struct rpi5_kernel_memory_map *out)
{
    const uint8_t *p=data;
    if (!p || !out || length<8 || rpi5_map_le(p,4)!=1) return -1;
    uint64_t count=rpi5_map_le(p+4,4);
    if (!count || count>64 || length!=8+count*24) return -1;
    unsigned normal=0,device=0;
    for (unsigned i=0;i<count;i++) {
        const uint8_t *r=p+8+i*24;
        uint64_t type=rpi5_map_le(r,8), start=rpi5_map_le(r+8,8), end=rpi5_map_le(r+16,8);
        if ((type!=1 && type!=2) || start>=end || end>(1ULL<<40) ||
            ((start|end)&0x3fff)) return -1;
        if (type==1) { if (device || ++normal>32) return -1; }
        else if (++device>32) return -1;
        for (unsigned j=0;j<i;j++) {
            const uint8_t *q=p+8+j*24;
            uint64_t qs=rpi5_map_le(q+8,8), qe=rpi5_map_le(q+16,8);
            if ((start<qe && qs<end) || (type==rpi5_map_le(q,8) && start<qe)) return -1;
        }
    }
    if (!normal) return -1;
    for (unsigned i=0;i<count;i++) {
        const uint8_t *r=p+8+i*24;
        out->type[i]=rpi5_map_le(r,8);
        out->start[i]=rpi5_map_le(r+8,8);
        out->end[i]=rpi5_map_le(r+16,8);
    }
    out->count=(unsigned)count;
    return 0;
}
/* Map must have been decoded successfully and remain immutable. Entire
 * interval must be covered by one type, including across adjacent records. */
static inline unsigned
rpi5_map_type(const struct rpi5_kernel_memory_map *map, uint64_t start, uint64_t end)
{
    if (!map || !map->count || map->count>64 || start>=end || end>(1ULL<<40)) return 0;
    unsigned type=0;
    uint64_t cursor=start;
    for (unsigned i=0;i<map->count;i++) {
        if (map->end[i]<=cursor || map->start[i]>cursor) continue;
        if (type && type!=map->type[i]) return 0;
        type=(unsigned)map->type[i];
        cursor=map->end[i];
        if (cursor>=end) return type;
    }
    return 0;
}
#endif
