/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_get.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REQUIRE(x) do {if(!(x)){fprintf(stderr,"failed:%d\n",__LINE__);return 1;}}while(0)

static void put(uint8_t *p,uint32_t value)
{ for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(8*i)); }
static uint32_t get(const uint8_t *p)
{
    uint32_t value=0;
    for(unsigned i=0;i<4;i++)value|=(uint32_t)p[i]<<(8*i);
    return value;
}
static void reply(uint8_t *p,size_t length,uint32_t value)
{
    put(p+4,0x80000000u);
    put(p+16,0x80000000u|(uint32_t)(length-24));
    put(p+20,value);
}
static int requests(void)
{
    _Alignas(16) uint8_t wire[128],before[128];
    const uint32_t spec[4][3]={{1,0,0},{2,1,0},{2,2,0},{2,2,1}};
    for(unsigned k=0;k<4;k++){
        memset(wire,0x5a,sizeof wire);size_t size=999;
        REQUIRE(!rpi5_display_get_request(spec[k][0],spec[k][1],spec[k][2],wire,sizeof wire,&size));
        size_t length=k?88:28;
        REQUIRE(size==length && get(wire)==length && get(wire+4)==0);
        REQUIRE(get(wire+8)==(k?0x40014u:0x40013u));
        REQUIRE(get(wire+12)==(k?64u:4u) && get(wire+16)==0);
        REQUIRE(get(wire+20)==spec[k][2]);
        for(size_t i=24;i<length;i++)REQUIRE(!wire[i]);
        for(size_t i=length;i<sizeof wire;i++)REQUIRE(wire[i]==0x5a);
        for(size_t capacity=0;capacity<length;capacity++){
            memset(wire,0xa5,sizeof wire);memcpy(before,wire,sizeof wire);size=777;
            REQUIRE(rpi5_display_get_request(spec[k][0],spec[k][1],spec[k][2],wire,capacity,&size));
            REQUIRE(size==777 && !memcmp(wire,before,sizeof wire));
        }
    }
    const uint32_t invalid[][3]={{0,0,0},{3,0,0},{0x40001,0,0},{0x48001,0,0},
        {0x48003,0,0},{0x48005,0,0},{0x48013,0,0},{0x40013,0,0},{0x40014,0,0},
        {UINT32_MAX,0,0},{1,1,0},{1,0,1},{2,0,0},{2,3,0},{2,2,2},
        {2,1,1},{2,UINT32_MAX,0},{2,2,UINT32_MAX}};
    for(size_t i=0;i<sizeof invalid/sizeof invalid[0];i++){
        memset(wire,0xa5,sizeof wire);memcpy(before,wire,sizeof wire);size_t size=777;
        REQUIRE(rpi5_display_get_request(invalid[i][0],invalid[i][1],invalid[i][2],wire,sizeof wire,&size));
        REQUIRE(size==777 && !memcmp(wire,before,sizeof wire));
    }
    for(unsigned offset=1;offset<16;offset++){
        memset(wire,0xa5,sizeof wire);memcpy(before,wire,sizeof wire);size_t size=777;
        REQUIRE(rpi5_display_get_request(1,0,0,wire+offset,112,&size));
        REQUIRE(size==777 && !memcmp(wire,before,sizeof wire));
    }
    size_t size=777;
    REQUIRE(rpi5_display_get_request(1,0,0,NULL,sizeof wire,&size));
    REQUIRE(size==777);
    memset(wire,0xa5,sizeof wire);memcpy(before,wire,sizeof wire);
    REQUIRE(rpi5_display_get_request(1,0,0,wire,sizeof wire,NULL));
    REQUIRE(rpi5_display_get_request(1,0,0,wire,sizeof wire,(size_t *)(void *)wire));
    /* Publishing written must not alter any byte in declared wire capacity,
     * including the unused tail beyond the 28/88-byte message extent. */
    REQUIRE(rpi5_display_get_request(1,0,0,wire,sizeof wire,(size_t *)(void *)(wire+32)));
    REQUIRE(rpi5_display_get_request(2,2,1,wire,sizeof wire,(size_t *)(void *)(wire+96)));
    REQUIRE(rpi5_display_get_request(1,0,0,wire,SIZE_MAX,&size));
    REQUIRE(!memcmp(wire,before,sizeof wire));
    puts("DISPLAY_GET_REQUEST PASS MAX_INDEX=1 EXACT_LENGTHS=28,88 NO_TRANSPORT=1");
    return 0;
}
static int responses(void)
{
    _Alignas(16) uint8_t wire[128],saved[128];
    struct rpi5_display_get_reply out,before;
    memset(&before,0xa5,sizeof before);
    for(uint32_t count=0;count<=2;count++){
        size_t length=0;
        REQUIRE(!rpi5_display_get_request(1,0,0,wire,sizeof wire,&length));
        reply(wire,length,count);out=before;
        REQUIRE(!rpi5_display_get_response(1,0,0,wire,length,&out));
        REQUIRE(out.kind==1 && out.display_index==0 && out.word_count==1 && out.words[0]==count);
        for(unsigned i=1;i<16;i++)REQUIRE(!out.words[i]);
    }
    for(uint32_t index=0;index<2;index++){
        size_t length=0;
        REQUIRE(!rpi5_display_get_request(2,2,index,wire,sizeof wire,&length));
        reply(wire,length,index);
        /* These deliberately are not valid geometry/pointers. The only
         * returned promise is exact raw words, never a decoded framebuffer. */
        for(unsigned i=1;i<16;i++)put(wire+20+4*i,0xffffffffu-i*0x01010101u);
        memcpy(saved,wire,sizeof wire);out=before;
        REQUIRE(!rpi5_display_get_response(2,2,index,wire,length,&out));
        REQUIRE(out.kind==2 && out.display_index==index && out.word_count==16);
        for(unsigned i=0;i<16;i++)REQUIRE(out.words[i]==get(wire+20+i*4));
        REQUIRE(!memcmp(saved,wire,sizeof wire));
        out=before;
        REQUIRE(rpi5_display_get_response(2,2,index^1,wire,length,&out));
        REQUIRE(!memcmp(&out,&before,sizeof out));
    }
    puts("DISPLAY_GET_RESPONSE PASS RAW_WORDS=16 NO_FORMAT_OR_ADDRESS_AUTHORITY=1");
    return 0;
}
static int negatives(void)
{
    _Alignas(16) uint8_t wire[128],valid[128],before_wire[128];
    struct rpi5_display_get_reply out,before;
    memset(&before,0xa5,sizeof before);
    unsigned rejected=0;
    for(unsigned kind=1;kind<=2;kind++){
        uint32_t count=kind==2?2:0,index=kind==2?1:0;
        size_t length=0;
        memset(valid,0x6a,sizeof valid);
        REQUIRE(!rpi5_display_get_request(kind,count,index,valid,sizeof valid,&length));
        /* A request is not a response. */
        out=before;REQUIRE(rpi5_display_get_response(kind,count,index,valid,length,&out));
        REQUIRE(!memcmp(&out,&before,sizeof out));
        reply(valid,length,kind==2?index:2);
        const size_t offsets[6]={0,4,8,12,16,length-4};
        for(unsigned field=0;field<6;field++)for(unsigned bit=0;bit<32;bit++){
            memcpy(wire,valid,sizeof wire);wire[offsets[field]+bit/8]^=(uint8_t)(1u<<(bit%8));
            memcpy(before_wire,wire,sizeof wire);out=before;
            REQUIRE(rpi5_display_get_response(kind,count,index,wire,length,&out));
            REQUIRE(!memcmp(&out,&before,sizeof out) && !memcmp(wire,before_wire,sizeof wire));
            rejected++;
        }
        for(size_t truncated=0;truncated<length;truncated++){
            out=before;REQUIRE(rpi5_display_get_response(kind,count,index,valid,truncated,&out));
            REQUIRE(!memcmp(&out,&before,sizeof out));rejected++;
        }
        for(size_t extended=length+1;extended<=sizeof valid;extended++){
            out=before;REQUIRE(rpi5_display_get_response(kind,count,index,valid,extended,&out));
            REQUIRE(!memcmp(&out,&before,sizeof out));rejected++;
        }
        for(unsigned offset=1;offset<16;offset++){
            out=before;REQUIRE(rpi5_display_get_response(kind,count,index,valid+offset,length,&out));
            REQUIRE(!memcmp(&out,&before,sizeof out));rejected++;
        }
        memcpy(wire,valid,sizeof wire);put(wire+20,kind==2?2:3);
        out=before;REQUIRE(rpi5_display_get_response(kind,count,index,wire,length,&out));
        REQUIRE(!memcmp(&out,&before,sizeof out));
        out=before;REQUIRE(rpi5_display_get_response(kind,count,index,NULL,length,&out));
        REQUIRE(!memcmp(&out,&before,sizeof out));
        REQUIRE(rpi5_display_get_response(kind,count,index,valid,length,NULL));
        memcpy(wire,valid,sizeof wire);
        REQUIRE(rpi5_display_get_response(kind,count,index,wire,length,
            (struct rpi5_display_get_reply *)(void *)wire));
        REQUIRE(!memcmp(wire,valid,sizeof wire));
        for(uint32_t tag=0x40001u;tag<=0x40014u;tag++){
            out=before;REQUIRE(rpi5_display_get_response(tag,count,index,valid,length,&out));
            REQUIRE(!memcmp(&out,&before,sizeof out));
        }
    }
    REQUIRE(rejected==670);
    puts("DISPLAY_GET_NEGATIVE PASS FRAMING_TRUNCATION_ALIGN_CASES=670 OUTPUT_ATOMIC=1");
    return 0;
}
int main(int argc,char **argv)
{
    REQUIRE(argc==2);
    if(!strcmp(argv[1],"request"))return requests();
    if(!strcmp(argv[1],"response"))return responses();
    if(!strcmp(argv[1],"negative"))return negatives();
    return 73;
}
