/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_allocate_wire.h"
/* Raspberry Pi firmware Mailbox-property-interface and pinned Pi5 EDK2
 * 8e1779b538bcc1e6dc68d7df625394f933651d7a RpiFirmwareAllocFb provide
 * SET+ALLOCATE+GET framing. Linux80d4218 supplies SET_DISPLAY_NUM and raw
 * GET_DISPLAY_SETTINGS. Exact source bytes accompany the successor package.
 * This original implementation does not import either driver's code. */
struct tag { uint32_t id,bytes,value[4]; };
static const struct tag pre[]={ {0x40013,4,{0}}, {0x40014,64,{0}} };
static const struct tag select_display[]={ {0x48013,4,{0}} };
static const struct tag set[]={
    {0x48003,8,{1920,1080}}, {0x48004,8,{1920,1080}},
    {0x48005,4,{32}}, {0x48006,4,{0}}, {0x48007,4,{2}},
    {0x48009,8,{0,0}}, {0x4800a,16,{0,0,0,0}},
    {0x40001,8,{16384,0}}, {0x40008,4,{0}}
};
static const struct tag get[]={
    {0x40003,8,{0}}, {0x40004,8,{0}}, {0x40005,4,{0}},
    {0x40006,4,{0}}, {0x40007,4,{0}}, {0x40009,8,{0}},
    {0x4000a,16,{0}}, {0x40008,4,{0}}, {0x40014,64,{0}}
};
static int schema(uint32_t kind,const struct tag **tags,unsigned *count,size_t *bytes)
{
    switch(kind){
    case 1:*tags=pre;*count=2;break;
    case 2:*tags=select_display;*count=1;break;
    case 3:*tags=set;*count=9;break;
    case 4:*tags=get;*count=9;break;
    default:return -1;
    }
    *bytes=12;for(unsigned i=0;i<*count;i++)*bytes+=12+(*tags)[i].bytes;
    return *bytes>RPI5_DISPLAY_ALLOCATE_MAX_BYTES?-1:0;
}
static void put(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint32_t word(const uint8_t *p){uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(8*i);return v;}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&(x+na<=y||y+nb<=x);}
int rpi5_display_allocate_request(uint32_t kind,void *wire,size_t capacity,size_t *written)
{
    const struct tag *tags;unsigned count;size_t bytes;
    if(!wire||!written||((uintptr_t)wire&15)||schema(kind,&tags,&count,&bytes)||capacity<bytes||
        !apart(wire,capacity,written,sizeof *written))return -1;
    uint8_t result[RPI5_DISPLAY_ALLOCATE_MAX_BYTES]={0};put(result,(uint32_t)bytes);size_t pos=8;
    for(unsigned i=0;i<count;i++){
        put(result+pos,tags[i].id);put(result+pos+4,tags[i].bytes);
        for(unsigned j=0;j<tags[i].bytes/4&&j<4;j++)put(result+pos+12+j*4,tags[i].value[j]);
        pos+=12+tags[i].bytes;
    }
    for(size_t i=0;i<bytes;i++)((uint8_t *)wire)[i]=result[i];*written=bytes;return 0;
}
int rpi5_display_allocate_response(uint32_t kind,const void *wire,size_t length,
    struct rpi5_display_allocate_reply *out)
{
    const struct tag *tags;unsigned count;size_t bytes;
    if(!wire||!out||((uintptr_t)wire&15)||schema(kind,&tags,&count,&bytes)||length!=bytes||
        !apart(wire,length,out,sizeof *out))return -1;
    const uint8_t *p=wire;
    if(word(p)!=bytes||word(p+4)!=0x80000000u||word(p+bytes-4))return -1;
    struct rpi5_display_allocate_reply r={.kind=kind};size_t pos=8;
    for(unsigned i=0;i<count;i++){
        if(word(p+pos)!=tags[i].id||word(p+pos+4)!=tags[i].bytes||
            word(p+pos+8)!=(0x80000000u|tags[i].bytes))return -1;
        for(unsigned j=0;j<tags[i].bytes/4;j++){
            if(r.count>=30)return -1;
            r.words[r.count++]=word(p+pos+12+j*4);
        }
        pos+=12+tags[i].bytes;
    }
    if(pos!=bytes-4)return -1;*out=r;return 0;
}
int rpi5_display_allocate_preflight(const struct rpi5_display_allocate_reply *r)
{
    static const uint32_t expected[]={1,0,1920,1080,32,7680,1920,1080,0,0};
    if(!r||r->kind!=1||r->count!=17)return -1;
    for(unsigned i=0;i<10;i++)if(r->words[i]!=expected[i])return -1;
    return 0;
}
int rpi5_display_allocate_consistent(const struct rpi5_display_allocate_reply *a,
    const struct rpi5_display_allocate_reply *b)
{
    static const uint32_t expected[]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0};
    static const uint32_t settings[]={0,1920,1080,32,7680,1920,1080,0,0};
    if(!a||!b||a->kind!=3||a->count!=16||b->kind!=4||b->count!=30)return -1;
    for(unsigned i=0;i<13;i++)if(a->words[i]!=expected[i]||b->words[i]!=expected[i])return -1;
    if(!a->words[13]||a->words[14]<8294400||a->words[14]>16u*1024*1024||a->words[15]!=7680||b->words[13]!=7680)return -1;
    for(unsigned i=0;i<9;i++)if(b->words[14+i]!=settings[i])return -1;
    return 0;
}
