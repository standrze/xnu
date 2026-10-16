/* SPDX-License-Identifier: BSD-2-Clause */
#include "memory_type.h"
static int valid_list(const struct rpi5_ranges *r)
{
    if (r->count>32) return 0;
    for (size_t i=0;i<r->count;i++) {
        struct rpi5_range x=r->extent[i];
        if (x.start>=x.end || x.end>(1ull<<40) || ((x.start|x.end)&0x3fff) ||
            (i && r->extent[i-1].end>x.start)) return 0;
    }
    return 1;
}
int rpi5_memory_types_validate(const struct rpi5_memory_types *types)
{
    if (!types || !types->normal.count || !valid_list(&types->normal) ||
        !valid_list(&types->device)) return -1;
    for (size_t i=0;i<types->normal.count;i++)
        for (size_t j=0;j<types->device.count;j++)
            if (types->normal.extent[i].start<types->device.extent[j].end &&
                types->device.extent[j].start<types->normal.extent[i].end) return -1;
    return 0;
}
static int covered(const struct rpi5_ranges *r,struct rpi5_range q)
{
    uint64_t cursor=q.start;
    for (size_t i=0;i<r->count && cursor<q.end;i++) {
        if (r->extent[i].end<=cursor) continue;
        if (r->extent[i].start>cursor) return 0;
        cursor=r->extent[i].end;
    }
    return cursor>=q.end;
}
enum rpi5_memory_type rpi5_memory_type_for(const struct rpi5_memory_types *types,
    struct rpi5_range query)
{
    if (query.start>=query.end || query.end>(1ull<<40) ||
        rpi5_memory_types_validate(types)) return RPI5_MEMORY_UNKNOWN;
    if (covered(&types->normal,query)) return RPI5_MEMORY_NORMAL;
    if (covered(&types->device,query)) return RPI5_MEMORY_DEVICE;
    return RPI5_MEMORY_UNKNOWN;
}
static void put_le(uint8_t *p, uint64_t value, unsigned width)
{
    for (unsigned i=0;i<width;i++) p[i]=(uint8_t)(value>>(8*i));
}
int rpi5_memory_types_encode(const struct rpi5_memory_types *types,
    void *output, size_t capacity, size_t *written)
{
    if (!output || !written || rpi5_memory_types_validate(types)) return -1;
    size_t count=types->normal.count+types->device.count;
    size_t length=8+24*count;
    if (capacity<length) return -1;
    uint8_t *p=output;
    put_le(p,1,4);
    put_le(p+4,count,4);
    p+=8;
    for (unsigned kind=1;kind<=2;kind++) {
        const struct rpi5_ranges *r=kind==1 ? &types->normal : &types->device;
        for (size_t i=0;i<r->count;i++,p+=24) {
            put_le(p,kind,8);
            put_le(p+8,r->extent[i].start,8);
            put_le(p+16,r->extent[i].end,8);
        }
    }
    *written=length;
    return 0;
}
