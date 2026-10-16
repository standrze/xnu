/* SPDX-License-Identifier: BSD-2-Clause */
#include "framebuffer_descriptor.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REQUIRE(x) do { if(!(x)) {fprintf(stderr,"failed:%d\n",__LINE__);return 1;} } while(0)

static int planning(void)
{
    struct rpi5_fb_descriptor d={{0x20000004,0x20800000},8294400,1920,1080,7680,RPI5_FB_XRGB8888};
    struct rpi5_range ram[]={ {0,0x20400000},{0x20400000,0x40000000} };
    struct rpi5_range live[]={ {0,0x80000},{0x6000000,0x10000000} };
    struct rpi5_fb_plan result,before;
    memset(&before,0xa5,sizeof before);result=before;
    REQUIRE(!rpi5_fb_plan(&d,ram,2,live,2,&result));
    REQUIRE(result.retained_pages.start==0x20000000 && result.retained_pages.end==0x20800000);
    REQUIRE(result.framebuffer.allocation.start==d.allocation.start);
    REQUIRE(rpi5_fb_apple_text_compatible(&d));
    struct rpi5_fb_descriptor tiny=d;
    tiny.width=7;tiny.height=15;tiny.stride=28;tiny.visible_bytes=420;
    REQUIRE(!rpi5_fb_apple_text_compatible(&tiny));
    REQUIRE(!rpi5_fb_plan(&tiny,ram,2,live,2,&result));
    for(unsigned format=2;format<=4;format++){
        d.format=format;REQUIRE(!rpi5_fb_apple_text_compatible(&d));
        REQUIRE(!rpi5_fb_plan(&d,ram,2,live,2,&result));
    }
    d.format=RPI5_FB_XRGB8888;
    for(unsigned i=0;i<13;i++){
        struct rpi5_fb_descriptor bad=d;
        switch(i){
            case 0:bad.width=0;break;case 1:bad.width=1921;break;
            case 2:bad.height=1081;break;case 3:bad.stride=7679;break;
            case 4:bad.stride=8196;break;case 5:bad.allocation.start=0;break;
            case 6:bad.allocation.start++;break;case 7:bad.allocation.end=bad.allocation.start;break;
            case 8:bad.allocation.end=(1ull<<40)+1;break;case 9:bad.format=0;break;
            case 10:bad.visible_bytes--;break;case 11:bad.allocation.end=0x20100000;break;
            case 12:bad.allocation.end=bad.allocation.start+16*1024*1024+1;break;
        }
        result=before;REQUIRE(rpi5_fb_plan(&bad,ram,2,live,2,&result));
        REQUIRE(!memcmp(&result,&before,sizeof result));
        REQUIRE(!rpi5_fb_apple_text_compatible(&bad));
    }
    for(unsigned i=0;i<4;i++){
        struct rpi5_range occupied[1];
        if(i==0)occupied[0]=(struct rpi5_range){d.allocation.start,d.allocation.start+1};
        if(i==1)occupied[0]=(struct rpi5_range){0x20000000,0x20000004}; /* rounded prefix */
        if(i==2)occupied[0]=(struct rpi5_range){4,4};
        if(i==3)occupied[0]=(struct rpi5_range){1,UINT64_MAX};
        result=before;REQUIRE(rpi5_fb_plan(&d,ram,2,occupied,1,&result));
        REQUIRE(!memcmp(&result,&before,sizeof result));
    }
    ram[1].start++;result=before;
    REQUIRE(rpi5_fb_plan(&d,ram,2,live,2,&result));
    REQUIRE(!memcmp(&result,&before,sizeof result));
    ram[1].start--;ram[0].start=0x20000004;result=before;
    REQUIRE(rpi5_fb_plan(&d,ram,2,live,2,&result)); /* visible backed, page prefix not */
    REQUIRE(!memcmp(&result,&before,sizeof result));
    puts("FRAMEBUFFER_PLAN PASS ATOMIC=1 FULL_ALLOCATION_RETAINED=1 NO_MAPPING=1");
    return 0;
}

int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"plan"))return planning();
    REQUIRE(argc==5);
    FILE *f=fopen(argv[1],"rb");REQUIRE(f);
    REQUIRE(!fseek(f,0,SEEK_END));long length=ftell(f);REQUIRE(length>=0 && length<=1024*1024);
    REQUIRE(!fseek(f,0,SEEK_SET));
    unsigned char *data=malloc((size_t)length+1);REQUIRE(data);
    REQUIRE(fread(data,1,(size_t)length,f)==(size_t)length);fclose(f);
    struct rpi5_fb_descriptor out,before;
    memset(&before,0x5a,sizeof before);out=before;
    int rc=rpi5_fb_from_fdt(data,(size_t)length,argv[2],&out);
    if(!strcmp(argv[3],"reject")){
        REQUIRE(rc && !memcmp(&out,&before,sizeof out));
        puts("FRAMEBUFFER_REJECT ATOMIC=1 NO_MMIO=1");
    }else{
        REQUIRE(!rc && out.width==1920 && out.height==1080 && out.stride==7680 &&
                out.visible_bytes==8294400 && out.allocation.end-out.allocation.start==8388608);
        REQUIRE(rpi5_fb_apple_text_compatible(&out)==atoi(argv[4]));
        puts("FRAMEBUFFER_DESCRIPTOR PASS NO_SCANOUT_CLAIM=1 NO_MMIO=1");
    }
    /* Every prefix truncation is malformed, and leaves output untouched. */
    for(size_t size=0;size<(size_t)length;size++){
        out=before;REQUIRE(rpi5_fb_from_fdt(data,size,argv[2],&out));
        REQUIRE(!memcmp(&out,&before,sizeof out));
    }
    free(data);return 0;
}
