/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_visible_patch.h"
extern unsigned char iso_font[256*16]; /* Unchanged original Apple font TU. */
uint32_t rpi5_display_visible_pixel(unsigned x,unsigned y)
{
    static const uint32_t colors[]={0x00ff0000,0x0000ff00,0x000000ff,0,0x00ffffff};
    static const unsigned char title[]="PI5 DISPLAY PROOF";
    static const unsigned char zero[]="ZERO ALPHA",opaque[]="OPAQUE ALPHA";
    if(x>=320||y>=64)return 0;
    unsigned half=x/160,local=x%160;uint32_t rgb=0;
    if(y<32)rgb=colors[local/32];
    else {
        const unsigned char *label=y<48?title:half?opaque:zero;
        unsigned length=y<48?sizeof title-1:half?sizeof opaque-1:sizeof zero-1;
        if(local/8<length&&((iso_font[label[local/8]*16+(y&15)]>>(local&7))&1))rgb=0x00ffffff;
    }
    return rgb|(half?0xff000000:0);
}
static int now(const struct rpi5_display_visible_ops *ops,struct rpi5_display_visible_report *r)
{
    uint64_t n;r->time_calls++;
    if(ops->now_us(ops->opaque,&n)||n<r->last_us||n>=r->deadline_us)return -1;
    r->last_us=n;return 0;
}
static int guard(const struct rpi5_display_visible_ops *ops,struct rpi5_display_visible_report *r)
{r->guard_calls++;return ops->current(ops->opaque);}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&!(x<y+nb&&y<x+na);}
static int stable(const struct rpi5_display_retained *a,const struct rpi5_display_retained *b,
    const struct rpi5_display_visible_ops *x,const struct rpi5_display_visible_ops *y)
{
    return a->framebuffer.allocation.start==b->framebuffer.allocation.start&&a->framebuffer.allocation.end==b->framebuffer.allocation.end&&
        a->framebuffer.visible_bytes==b->framebuffer.visible_bytes&&a->framebuffer.width==b->framebuffer.width&&
        a->framebuffer.height==b->framebuffer.height&&a->framebuffer.stride==b->framebuffer.stride&&a->framebuffer.format==b->framebuffer.format&&
        a->retained_pages.start==b->retained_pages.start&&a->retained_pages.end==b->retained_pages.end&&a->fresh_low_ram_end==b->fresh_low_ram_end&&
        x->opaque==y->opaque&&x->current==y->current&&x->now_us==y->now_us&&x->store32==y->store32&&x->barrier==y->barrier;
}
int rpi5_display_visible_patch(const struct rpi5_display_retained *input,
    const struct rpi5_display_visible_ops *callbacks,struct rpi5_display_visible_report *r)
{
    if(!input||!callbacks||!r||r->used||!callbacks->current||!callbacks->now_us||!callbacks->store32||!callbacks->barrier||
        !apart(input,sizeof *input,r,sizeof *r)||!apart(callbacks,sizeof *callbacks,r,sizeof *r))return -1;
    if(r->first_address||r->last_address||r->start_us||r->last_us||r->deadline_us||r->attempted||r->completed||
        r->rows||r->guard_calls||r->time_calls||r->barriers||(r->result&&r->result!=-2))return -1;
    r->used=1;r->result=-1;struct rpi5_display_retained retained=*input;
    struct rpi5_display_visible_ops ops=*callbacks;
    const struct rpi5_fb_descriptor *d=&retained.framebuffer;
    if(d->width!=1920||d->height!=1080||d->stride!=7680||d->format!=RPI5_FB_XRGB8888||d->visible_bytes!=8294400||
        !d->allocation.start||(d->allocation.start&16383)||d->allocation.start<0x3e000000||
        d->allocation.end<=d->allocation.start||d->allocation.end>0x40000000||
        d->allocation.end-d->allocation.start<8294400||d->allocation.end-d->allocation.start>16*1024*1024||
        retained.retained_pages.start!=d->allocation.start||retained.retained_pages.end!=((d->allocation.end+16383)&~UINT64_C(16383)))return -1;
    r->first_address=d->allocation.start+16*7680+16*4;
    r->last_address=d->allocation.start+79*7680+335*4;
    if(r->last_address+4>d->allocation.end||guard(&ops,r))return -1;
    r->time_calls++;
    if(ops.now_us(ops.opaque,&r->start_us)||r->start_us>UINT64_MAX-RPI5_VISIBLE_US)return -1;
    r->last_us=r->start_us;r->deadline_us=r->start_us+RPI5_VISIBLE_US;
    for(unsigned y=0;y<64;y++){
        if(!stable(input,&retained,callbacks,&ops)||guard(&ops,r)||now(&ops,r))return -1;
        for(unsigned x=0;x<320;x++){
            uint64_t address=d->allocation.start+(y+16)*7680+(x+16)*4;
            if((address&3)||address<r->first_address||address>r->last_address||address+4>d->allocation.end||
                r->attempted>=RPI5_VISIBLE_STORES||!stable(input,&retained,callbacks,&ops)||now(&ops,r))return -1;
            r->attempted++;
            if(ops.store32(ops.opaque,address,rpi5_display_visible_pixel(x,y)))return -1;
            r->completed++;
        }
        r->barriers++;
        if(ops.barrier(ops.opaque)||!stable(input,&retained,callbacks,&ops)||guard(&ops,r)||now(&ops,r))return -1;
        r->rows++;
    }
    if(r->attempted!=RPI5_VISIBLE_STORES||r->completed!=RPI5_VISIBLE_STORES||r->rows!=64)return -1;
    r->result=0;return 0;
}
