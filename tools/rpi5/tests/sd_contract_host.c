/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sd_contract.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void le(uint8_t *p, uint64_t value, unsigned size)
{
    for (unsigned i=0;i<size;i++) p[i]=(uint8_t)(value>>(i*8));
}
int main(void)
{
    uint8_t host[32],power[48],variant[4]={0},clock[4],settle[4],irq[4];
    const uint64_t base[5]={0x1000fff000ull,0x1000fff400ull,0x107d517c00ull,0x107d504100ull,0x107d510700ull};
    const unsigned sizes[5]={0x260,0x200,0x40,0x30,0x20};
    for (unsigned i=0;i<5;i++) {
        uint8_t *p=i<2 ? host+i*16 : power+(i-2)*16;
        le(p,base[i],8); le(p+8,sizes[i],8);
    }
    le(clock,200000000,4); le(settle,5000,4); le(irq,305,4);
    struct rpi5_sd_binding out,previous;
    memset(&previous,0xa5,sizeof previous);
#define DECODE() rpi5_sd_binding_decode(host,sizeof host,power,sizeof power,variant,sizeof variant,clock,sizeof clock,settle,sizeof settle,irq,sizeof irq,&out)
    assert(!DECODE());
    for (unsigned i=0;i<5;i++) assert(out.base[i]==base[i] && out.size[i]==sizes[i]);
    assert(!out.variant && out.settling_us==5000 && out.source_hz==200000000);
    variant[0]=1; assert(!DECODE() && out.variant==1); variant[0]=0;
    struct {uint8_t *data; unsigned size;} fields[]={
        {host,sizeof host},{power,sizeof power},{clock,sizeof clock},{settle,sizeof settle},{irq,sizeof irq},
    };
    for (unsigned i=0;i<sizeof fields/sizeof fields[0];i++) for (unsigned j=0;j<fields[i].size;j++) {
        fields[i].data[j]^=1; out=previous;
        assert(DECODE()==-1 && !memcmp(&out,&previous,sizeof out));
        fields[i].data[j]^=1;
    }
    variant[0]=2; out=previous;
    assert(DECODE()==-1 && !memcmp(&out,&previous,sizeof out)); variant[0]=0;
    for (unsigned size=0;size<sizeof host;size++) {
        out=previous;
        assert(rpi5_sd_binding_decode(host,size,power,sizeof power,variant,4,clock,4,settle,4,irq,4,&out)==-1);
        assert(!memcmp(&out,&previous,sizeof out));
    }
    assert(rpi5_sd_binding_decode(0,32,power,48,variant,4,clock,4,settle,4,irq,4,&out)==-1);
    assert(!rpi5_sd_read_request_valid(0,0,1,512));
    assert(!rpi5_sd_read_request_valid(100,0,0,0));
    assert(!rpi5_sd_read_request_valid(100,0,33,33*512));
    assert(!rpi5_sd_read_request_valid(100,100,1,512));
    assert(!rpi5_sd_read_request_valid(100,99,2,1024));
    assert(!rpi5_sd_read_request_valid(100,0,1,511));
    assert(!rpi5_sd_read_request_valid(UINT64_MAX,UINT64_MAX,UINT64_MAX,UINT64_MAX));
    assert(rpi5_sd_read_request_valid(100,68,32,32*512));
    assert(rpi5_sd_read_request_valid(UINT64_C(1)<<32,UINT32_MAX,1,512));
    assert(!rpi5_sd_read_request_valid(UINT64_C(1)<<32,UINT32_MAX,2,1024));
    assert(!rpi5_sd_read_request_valid((UINT64_C(1)<<32)+1,0,1,512));
    struct rpi5_sd_request_queue q={.accepting=1};
    struct rpi5_sd_request_link items[RPI5_SD_MAX_REQUESTS+1]={0};
    for (unsigned i=0;i<RPI5_SD_MAX_REQUESTS;i++) assert(!rpi5_sd_queue_push(&q,&items[i]));
    struct rpi5_sd_request_queue saved=q;
    assert(rpi5_sd_queue_push(&q,&items[32])==-1 && !memcmp(&q,&saved,sizeof q));
    assert(rpi5_sd_queue_pop(&q)==&items[0] && q.active==1 && q.queued==31);
    assert(!rpi5_sd_queue_pop(&q)); /* No second consumer while one request is active. */
    assert(rpi5_sd_queue_push(&q,&items[32])==-1);
    assert(!rpi5_sd_queue_complete(&q));
    assert(rpi5_sd_queue_complete(&q)==-1); /* Never decrement an inactive request. */
    assert(!rpi5_sd_queue_push(&q,&items[32]));
    q.accepting=0; saved=q;
    assert(rpi5_sd_queue_push(&q,&items[0])==-1 && !memcmp(&q,&saved,sizeof q));
    for (unsigned i=1;i<=RPI5_SD_MAX_REQUESTS;i++) {
        assert(rpi5_sd_queue_pop(&q)==&items[i]);
        assert(!rpi5_sd_queue_complete(&q));
    }
    assert(!q.head && !q.tail && !q.queued && !q.active && !rpi5_sd_queue_pop(&q));
    puts("SD_CONTRACT_PASS");
    return 0;
}
