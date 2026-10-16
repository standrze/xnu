/* SPDX-License-Identifier: BSD-2-Clause */
#include "framebuffer_observation.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static char output[32768];static size_t used,calls,fail_at;
static int text(const char *s){calls++;if(fail_at && calls>=fail_at)return 0;
    size_t n=strlen(s);assert(used+n<sizeof(output));memcpy(output+used,s,n);used+=n;output[used]=0;return 1;}
static int hex(uint64_t v){char b[19];snprintf(b,sizeof(b),"0x%016llX",(unsigned long long)v);return text(b);}
int main(int argc,char **argv){
    if(argc==2 && !strcmp(argv[1],"formatter")){
        struct rpi5_fb_observation o={0};o.count=1;o.node[0].kind=1;strcpy(o.node[0].path,"/chosen/framebuffer@20000000");
        o.node[0].descriptor_rc=-1;o.node[0].plan_rc=-1;
        assert(!rpi5_fb_observation_log(&o,text,hex));size_t total=calls;assert(used<32768);
        for(size_t i=1;i<=total;i++){used=calls=0;fail_at=i;assert(rpi5_fb_observation_log(&o,text,hex));assert(calls==i);}
        fail_at=used=calls=0;memset(o.node[0].path,'a',sizeof(o.node[0].path));o.node[0].path[0]='/';
        assert(rpi5_fb_observation_log(&o,text,hex) && !calls);
        strcpy(o.node[0].path,"/chosen\nEVIL");assert(rpi5_fb_observation_log(&o,text,hex) && !calls);
        strcpy(o.node[0].path,"/chosen");o.reservations.count=1;o.reservations.request[0].window_count=9;
        assert(rpi5_fb_observation_log(&o,text,hex) && !calls);
        memset(&o,0,sizeof(o));o.count=4;o.memory.count=8;o.reservations.fixed.count=32;o.reservations.count=8;
        for(unsigned i=0;i<8;i++)o.reservations.request[i].window_count=8;
        for(unsigned i=0;i<4;i++){o.node[i].kind=1;memset(o.node[i].path,'x',sizeof(o.node[i].path));
            o.node[i].path[0]='/';o.node[i].path[sizeof(o.node[i].path)-1]=0;}
        assert(!rpi5_fb_observation_log(&o,text,hex) && used<32768);
        puts("FORMATTER PASS BOUNDED=1 FAIL_STOP=1");return 0;
    }
    assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);assert(!fseek(f,0,SEEK_END));long length=ftell(f);assert(length>=0);
    rewind(f);unsigned char *raw=malloc((size_t)length+1);assert(raw);assert(fread(raw,1,(size_t)length,f)==(size_t)length);fclose(f);
    struct rpi5_fb_observation o,before;memset(&o,0xa5,sizeof(o));before=o;
    struct rpi5_range live[]={{0x9000000,0x9100000},{0x207fc000,0x20800000}};
    struct rpi5_fb_observation scratch,comparison;
    int rc=rpi5_fb_observe_with_scratch(raw,(size_t)length,live,2,&o,&scratch);
    memset(&comparison,0xa5,sizeof(comparison));int other=rpi5_fb_observe(raw,(size_t)length,live,2,&comparison);
    assert(rc==other && !memcmp(&o,&comparison,sizeof(o)));
    assert(rpi5_fb_observe_with_scratch(raw,(size_t)length,live,2,&o,&o));
    if(!strcmp(argv[2],"reject")){assert(rc && !memcmp(&o,&before,sizeof(o)));puts("REJECT ATOMIC=1");}
    else{assert(!rc);assert(!rpi5_fb_observation_log(&o,text,hex));assert(used<32768);fputs(output,stdout);}
    free(raw);return 0;
}
