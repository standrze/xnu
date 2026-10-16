/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_XNU_RECORD_H
#define RPI5_DISPLAY_XNU_RECORD_H
#include <stdint.h>
#include <stddef.h>
#define RPI5_DISPLAY_XNU_RECORD_BYTES 192u
/* Private same-boot loader contract. Physical type is distinct from managed
 * availability and allocation ownership. No kernel client may infer this
 * record from an old serial transcript, previous reset, simplefb or RAM hole. */
struct rpi5_display_xnu_record {
    uint64_t base,bytes,reserve_start,reserve_end,width,height,stride,depth,order,alpha;
    uint64_t managed_start,managed_end,loader_start,loader_end,top,fdt,fdt_bytes;
    uint64_t owner_counter,fresh_low_ram_end;
};
static inline uint64_t rpi5_display_xnu_le(const uint8_t *p)
{uint64_t n=0;for(unsigned i=0;i<8;i++)n|=(uint64_t)p[i]<<(8*i);return n;}
static inline int rpi5_display_xnu_record_valid(const struct rpi5_display_xnu_record *r)
{
    if(!r||!r->base||(r->base&16383)||r->base<0x3e000000||r->base>=0x40000000||
        r->bytes!=8294400||r->reserve_start!=r->base||r->reserve_end!=((r->base+r->bytes+16383)&~UINT64_C(16383))||
        r->reserve_end>0x40000000||r->width!=1920||r->height!=1080||r->stride!=7680||r->depth!=32||r->order||r->alpha!=2||
        r->managed_start!=0x6000000||r->managed_end!=0x10000000||r->loader_start!=0x9000000||
        r->loader_end<=r->loader_start||r->loader_end>r->top||(r->top&16383)||r->top>r->managed_end||
        r->top<r->managed_start||r->fdt<r->loader_end||(r->fdt&7)||r->fdt_bytes<40||r->fdt_bytes>1048576||
        r->fdt>r->top||r->fdt_bytes>r->top-r->fdt||!r->owner_counter||
        r->fresh_low_ram_end<0x3e000000||r->fresh_low_ram_end>0x3fc00000||r->base<r->fresh_low_ram_end||
        (r->base<r->managed_end&&r->managed_start<r->reserve_end))return -1;
    return 0;
}
static inline int rpi5_display_xnu_record_decode(const void *data,size_t length,
    struct rpi5_display_xnu_record *out)
{
    if(!data||!out||length!=RPI5_DISPLAY_XNU_RECORD_BYTES)return -1;
    const uint8_t *p=data;
    if(rpi5_display_xnu_le(p)!=1||rpi5_display_xnu_le(p+8)!=1||rpi5_display_xnu_le(p+21*8)!=16384||
        rpi5_display_xnu_le(p+22*8)||rpi5_display_xnu_le(p+23*8))return -1;
    struct rpi5_display_xnu_record r;
    uint64_t *fields[]={&r.base,&r.bytes,&r.reserve_start,&r.reserve_end,&r.width,&r.height,&r.stride,&r.depth,&r.order,&r.alpha,
        &r.managed_start,&r.managed_end,&r.loader_start,&r.loader_end,&r.top,&r.fdt,&r.fdt_bytes,&r.owner_counter,&r.fresh_low_ram_end};
    for(unsigned i=0;i<19;i++)*fields[i]=rpi5_display_xnu_le(p+(i+2)*8);
    if(rpi5_display_xnu_record_valid(&r))return -1;
    *out=r;return 0;
}
static inline int rpi5_display_xnu_record_encode(const struct rpi5_display_xnu_record *r,
    void *output,size_t capacity)
{
    if(!output||capacity<RPI5_DISPLAY_XNU_RECORD_BYTES||rpi5_display_xnu_record_valid(r))return -1;
    const uint64_t values[]={1,1,r->base,r->bytes,r->reserve_start,r->reserve_end,r->width,r->height,r->stride,r->depth,r->order,r->alpha,
        r->managed_start,r->managed_end,r->loader_start,r->loader_end,r->top,r->fdt,r->fdt_bytes,r->owner_counter,r->fresh_low_ram_end,16384,0,0};
    uint8_t bytes[RPI5_DISPLAY_XNU_RECORD_BYTES];
    for(unsigned n=0;n<24;n++)for(unsigned i=0;i<8;i++)bytes[n*8+i]=(uint8_t)(values[n]>>(8*i));
    uint8_t *p=output;for(unsigned i=0;i<sizeof bytes;i++)p[i]=bytes[i];return 0;
}
/* Exact live Boot_Video identity; bit0 is Apple's physical-address marker.
 * No arbitrary virtual framebuffer, offsets, rotation, scale or length. */
static inline int rpi5_display_xnu_video_valid(const struct rpi5_display_xnu_record *r,
    uint64_t base,uint64_t width,uint64_t height,uint64_t stride,uint64_t depth,
    uint64_t offset,uint64_t length,uint64_t rotate,uint64_t scale)
{
    return !rpi5_display_xnu_record_valid(r)&&base==(r->base|1)&&width==r->width&&height==r->height&&
        stride==r->stride&&depth==32&&!offset&&!length&&!rotate&&scale==1?0:-1;
}
/* Pure admission policy.0=outside the framebuffer,-1=unsafe overlap,
 *1=exact owned Normal-NC request. Actual pmap supplies its own WCOMB constant
 * and proves NX/PNX in the selected PTE path; policy never creates mappings. */
static inline int rpi5_display_xnu_map_policy(const struct rpi5_display_xnu_record *r,
    uint64_t start,uint64_t end,unsigned wcomb,int nx,int early)
{
    if(rpi5_display_xnu_record_valid(r)||start>=end)return -1;
    if(start>=r->reserve_end||end<=r->reserve_start)return 0;
    if(start<r->reserve_start||end>r->reserve_end||((start|end)&16383)||!wcomb||!nx||
        (early&&(start!=r->reserve_start||end!=r->reserve_end)))return -1;
    return 1;
}
#endif
