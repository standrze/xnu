/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_allocate_wire.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static uint32_t get(const unsigned char *p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put(unsigned char *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
int main(void)
{
    _Alignas(16) unsigned char wire[512],request[512],response[512];unsigned tested=0;
    for(unsigned kind=1;kind<=4;kind++){
        memset(wire,0xa5,sizeof wire);size_t n=0;
        assert(!rpi5_display_allocate_request(kind,wire,sizeof wire,&n));
        assert(n==(kind==1?104:kind==2?28:kind==3?184:240));
        for(size_t i=n;i<sizeof wire;i++)assert(wire[i]==0xa5);
        assert(!get(wire+4)&&!get(wire+n-4));memcpy(request,wire,sizeof wire);
        put(wire+4,0x80000000);
        for(size_t p=8;p<n-4;){assert(!get(wire+p+8));put(wire+p+8,0x80000000|get(wire+p+4));p+=12+get(wire+p+4);}
        memcpy(response,wire,sizeof wire);
        struct rpi5_display_allocate_reply out,prior;memset(&prior,0xa5,sizeof prior);out=prior;
        assert(!rpi5_display_allocate_response(kind,wire,n,&out));
        // Every framing/header bit is fail-closed, not only a selected sample.
        unsigned char framing[512]={0};memset(framing,1,8);memset(framing+n-4,1,4);
        for(size_t p=8;p<n-4;){memset(framing+p,1,12);p+=12+get(wire+p+4);}
        for(size_t i=0;i<n;i++)if(framing[i])for(unsigned bit=0;bit<8;bit++){
            memcpy(wire,response,sizeof wire);wire[i]^=1u<<bit;out=prior;
            assert(rpi5_display_allocate_response(kind,wire,n,&out));assert(!memcmp(&out,&prior,sizeof out));tested++;
        }
        memcpy(wire,response,sizeof wire);
        for(size_t len=0;len<n;len++){out=prior;assert(rpi5_display_allocate_response(kind,wire,len,&out));assert(!memcmp(&out,&prior,sizeof out));}
        out=prior;assert(rpi5_display_allocate_response(kind,wire,n+4,&out));assert(!memcmp(&out,&prior,sizeof out));
        for(size_t cap=0;cap<n;cap++){size_t written=0xdead;memcpy(wire,request,sizeof wire);assert(rpi5_display_allocate_request(kind,wire,cap,&written));assert(written==0xdead&&!memcmp(wire,request,sizeof wire));}
        memcpy(wire,request,sizeof wire);assert(rpi5_display_allocate_request(kind,wire,sizeof wire,(size_t *)(wire+480)));assert(!memcmp(wire,request,sizeof wire));
        size_t written=99;assert(rpi5_display_allocate_request(kind,wire,SIZE_MAX,&written));assert(written==99);
    }
    for(unsigned k=0;k<32;k++)if(k<1||k>4){size_t n=99;memset(wire,0xa5,sizeof wire);assert(rpi5_display_allocate_request(k,wire,sizeof wire,&n));assert(n==99);}
    struct rpi5_display_allocate_reply p={.kind=1,.count=17,.words={1,0,1920,1080,32,7680,1920,1080,0,0}};
    assert(!rpi5_display_allocate_preflight(&p));for(unsigned i=0;i<10;i++){p.words[i]^=1;assert(rpi5_display_allocate_preflight(&p));p.words[i]^=1;}
    struct rpi5_display_allocate_reply a={.kind=3,.count=16,.words={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,0xff400000,8294400,7680}};
    struct rpi5_display_allocate_reply b={.kind=4,.count=30,.words={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,7680,0,1920,1080,32,7680,1920,1080,0,0}};
    assert(!rpi5_display_allocate_consistent(&a,&b));
    for(unsigned i=0;i<13;i++){a.words[i]^=1;assert(rpi5_display_allocate_consistent(&a,&b));a.words[i]^=1;}
    for(unsigned i=0;i<23;i++){b.words[i]^=1;assert(rpi5_display_allocate_consistent(&a,&b));b.words[i]^=1;}
    printf("WIRE framing_faults=%u ATOMIC=1 NO_HARDWARE=1\n",tested);return 0;
}
