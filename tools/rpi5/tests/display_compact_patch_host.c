/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit store/time/owner doubles; ordinary canary RAM, never hardware. */
#include "display_compact_patch.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char guarded[608128];
static unsigned stores,guards,barriers,times,mode,fail;
static uint64_t clock_us;
static struct rpi5_display_compact_ops *live_ops;
static struct rpi5_display_retained *live_retained;
static int current(void *p){assert(p==guarded);guards++;return mode==1&&guards==fail?-1:0;}
static int now(void *p,uint64_t *out){assert(p==guarded);times++;clock_us++;*out=clock_us;
    if(mode==2&&times==fail)*out=times==1?UINT64_MAX:*out+500000;
    if(mode==3&&times==fail)*out=times==1?UINT64_MAX:0;
    return mode==4&&times==fail?-1:0;}
static int store(void *p,uint64_t address,uint32_t value){assert(p==guarded);
    unsigned x=stores%96,y=stores/96;
    assert(address==UINT64_C(0x3f400000)+(y+16)*7680+(x+16)*4);
    assert(value==rpi5_display_compact_pixel(x,y));stores++;
    if(mode==5&&stores==fail)return -1;
    memcpy(guarded+32+address-0x3f400000,&value,4);
    if(mode==10&&stores==1)live_ops->store32=0;
    if(mode==11&&stores==1)live_retained->framebuffer.allocation.start+=16384;
    return 0;}
static int barrier(void *p){assert(p==guarded);barriers++;return mode==6&&barriers==fail?-1:0;}
int main(int argc,char **argv){assert(argc==3);mode=(unsigned)strtoul(argv[1],0,10);fail=(unsigned)strtoul(argv[2],0,10);
    memset(guarded,0xa5,sizeof guarded);
    struct rpi5_display_retained retained={.framebuffer={{0x3f400000,0x3fbe9000},8294400,1920,1080,7680,RPI5_FB_XRGB8888},.retained_pages={0x3f400000,0x3fbec000},.fresh_low_ram_end=0x3f400000};
    struct rpi5_display_compact_ops ops={guarded,current,now,store,barrier};
    struct rpi5_display_compact_report report={0};
    live_ops=&ops;live_retained=&retained;
    if(mode==7)retained.framebuffer.stride=3840;
    if(mode==8)retained.retained_pages.end-=16384;
    if(mode==9)retained.framebuffer.allocation.start|=0xc0000000;
    if(mode==12)report.completed=1;
    int rc=rpi5_display_compact_patch(&retained,&ops,&report);
    if(mode)assert(rc&&(report.result||mode==12));
    else {
        assert(!rc&&!report.result&&report.attempted==768&&report.completed==768&&report.rows==8);
        assert(stores==768&&guards==17&&barriers==8&&times==785);
        assert(report.first_address==0x3f41e040&&report.last_address==0x3f42b3bc);
        for(unsigned offset=0;offset<608064;offset+=4){
            unsigned y=offset/7680,x=(offset%7680)/4;uint32_t actual;memcpy(&actual,guarded+32+offset,4);
            if(y>=16&&y<24&&x>=16&&x<112)assert(actual==rpi5_display_compact_pixel(x-16,y-16));
            else assert(actual==0xa5a5a5a5);
        }
        extern unsigned char iso_font[256*16];
        for(unsigned y=0;y<8;y++)for(unsigned x=0;x<96;x++){
            unsigned local=x%48;uint32_t expected=0;
            if(local>=24){const uint32_t c[]={0xff0000,0x00ff00,0x0000ff};expected=c[(local-24)/8];}
            else {const unsigned char label[]="PI5";expected=((iso_font[label[local/8]*16+y*2]>>(local%8))&1)?0xffffff:0;}
            expected|=x>=48?0xff000000:0;
            assert(rpi5_display_compact_pixel(x,y)==expected);
        }
        assert(!rpi5_display_compact_pixel(96,0)&&!rpi5_display_compact_pixel(0,8));
    }
    for(unsigned i=0;i<32;i++)assert(guarded[i]==0xa5&&guarded[608096+i]==0xa5);
    unsigned before=stores;assert(rpi5_display_compact_patch(&retained,&ops,&report));assert(stores==before);
    struct rpi5_display_compact_report alias={0};
    assert(rpi5_display_compact_patch((void *)&alias,&ops,&alias));
    assert(rpi5_display_compact_patch(&retained,(void *)&alias,&alias));
    printf("VISIBLE PATCH mode=%u stores=%u guards=%u times=%u barriers=%u HOST_DOUBLES_ONLY\n",mode,stores,guards,times,barriers);return 0;}

