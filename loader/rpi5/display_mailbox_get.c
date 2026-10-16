/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_get.h"

/* Primary facts, NOT a claim that these queries work on the current Pi:
 * raspberrypi/linux commit 80d4218cb877ccb07d09a9f21f0678e78d8b36f5
 * include/soc/bcm2835/raspberrypi-firmware.h: GET_NUM_DISPLAYS 0x40013,
 * GET_DISPLAY_SETTINGS 0x40014, GET_DISPLAY_SETTINGS_PAYLOAD_SIZE 64.
 * SHA256 4eef64f4ba698648299ea30978df83cc211728d6b7aba9fd1a04df627208e07e
 * drivers/video/fbdev/bcm2708_fb.c: probe supplies index directly in the
 * GET_DISPLAY_SETTINGS payload (no SET_DISPLAY_NUM required for that GET).
 * SHA256 ecdfa03f27085b49b5abdb6dcb6c13127613bb443d82819b1a0f1ae781c372c7
 * drivers/firmware/raspberrypi.c: 8-byte envelope, 12-byte tag header,
 * req_resp_size=0, 4-byte END, aligned property message, status 0x80000000.
 * SHA256 df915d2a2c74ac24c684b108930e4fcc37ae0daeac858c50c9961a278d5463cb
 * Canonical URLs are pinned in display_mailbox_get_sources.json. No Linux
 * native struct layout is copied: unsigned long/padding are not wire proof.
 */
static void put32(uint8_t *p, uint32_t v)
{ for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8)); }
static uint32_t get32(const uint8_t *p)
{
    uint32_t v=0;
    for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(i*8);
    return v;
}
static int schema(uint32_t kind,uint32_t count,uint32_t index,
    uint32_t *tag,uint32_t *payload)
{
    if(kind==RPI5_DISPLAY_GET_COUNT){
        if(count || index)return -1;
        *tag=0x00040013u;*payload=4;return 0;
    }
    if(kind==RPI5_DISPLAY_GET_SETTINGS){
        if(!count || count>RPI5_DISPLAY_GET_MAX_DISPLAYS || index>=count)return -1;
        *tag=0x00040014u;*payload=64;return 0;
    }
    /* ALLOCATE has a 0x400xx tag but is state-changing. There is deliberately
     * no generic tag-id/prefix interface, SET, ALLOCATE or RELEASE fallback. */
    return -1;
}
static int disjoint(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(na>UINTPTR_MAX-x || nb>UINTPTR_MAX-y)return 0;
    return x+na<=y || y+nb<=x;
}
int rpi5_display_get_request(uint32_t kind,uint32_t count,uint32_t index,
    void *wire,size_t capacity,size_t *written)
{
    uint32_t tag,payload;
    if(!wire || !written || ((uintptr_t)wire&(RPI5_DISPLAY_GET_ALIGNMENT-1)) ||
       schema(kind,count,index,&tag,&payload))return -1;
    size_t length=24u+payload;
    if(capacity<length || !disjoint(wire,capacity,written,sizeof *written))return -1;
    uint8_t result[RPI5_DISPLAY_GET_MAX_BYTES]={0};
    put32(result,(uint32_t)length);
    put32(result+8,tag);
    put32(result+12,payload);
    if(kind==RPI5_DISPLAY_GET_SETTINGS)put32(result+20,index);
    uint8_t *destination=wire;
    for(size_t i=0;i<length;i++)destination[i]=result[i];
    *written=length;
    return 0;
}
int rpi5_display_get_response(uint32_t kind,uint32_t count,uint32_t index,
    const void *wire,size_t length,struct rpi5_display_get_reply *out)
{
    uint32_t tag,payload;
    if(!wire || !out || ((uintptr_t)wire&(RPI5_DISPLAY_GET_ALIGNMENT-1)) ||
       schema(kind,count,index,&tag,&payload) || length!=24u+payload ||
       !disjoint(wire,length,out,sizeof *out))return -1;
    const uint8_t *p=wire;
    if(get32(p)!=length || get32(p+4)!=0x80000000u || get32(p+8)!=tag ||
       get32(p+12)!=payload || get32(p+16)!=(0x80000000u|payload) ||
       get32(p+20+payload))return -1;
    struct rpi5_display_get_reply result={0};
    result.kind=kind;result.display_index=index;result.word_count=payload/4;
    for(unsigned i=0;i<result.word_count;i++)result.words[i]=get32(p+20+i*4);
    if(kind==RPI5_DISPLAY_GET_COUNT){
        if(result.words[0]>RPI5_DISPLAY_GET_MAX_DISPLAYS)return -1;
    }else if(result.words[0]!=index)return -1;
    *out=result;
    return 0;
}
