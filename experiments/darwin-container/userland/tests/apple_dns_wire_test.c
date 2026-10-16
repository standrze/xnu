/* SPDX-License-Identifier: BSD-2-Clause
 * Native parser boundary fixture, not guest network execution evidence.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int apple_dns_answer(const unsigned char *,size_t,const unsigned char *,size_t,uint32_t *);
int main(void)
{
    const unsigned char query[]={0x58,0x4e,1,0,0,1,0,0,0,0,0,0,1,'a',6,'d','a','r','w','i','n',4,'t','e','s','t',0,0,1,0,1};
    unsigned char reply[sizeof(query)+16];memcpy(reply,query,sizeof(query));
    reply[2]=0x81;reply[3]=0x80;reply[7]=1;
    const unsigned char answer[]={0xc0,12,0,1,0,1,0,0,0,1,0,4,192,168,64,1};
    memcpy(reply+sizeof(query),answer,sizeof(answer));
    uint32_t ip=0;const unsigned char expected[]={192,168,64,1};
    assert(apple_dns_answer(query,sizeof(query),reply,sizeof(reply),&ip)==0 && !memcmp(&ip,expected,4));
    for(size_t n=0;n<sizeof(reply);n++) assert(apple_dns_answer(query,sizeof(query),reply,n,&ip)==-1);
    reply[sizeof(query)+1]=(unsigned char)sizeof(query); /* compressed name points to itself */
    assert(apple_dns_answer(query,sizeof(query),reply,sizeof(reply),&ip)==-1);
    reply[sizeof(query)+1]=255;
    assert(apple_dns_answer(query,sizeof(query),reply,sizeof(reply),&ip)==-1);
    reply[sizeof(query)+1]=12;reply[1]^=1;
    assert(apple_dns_answer(query,sizeof(query),reply,sizeof(reply),&ip)==-1);
    puts("Original Apple DNS wire parser: valid compressed A, all truncations, loop/out-of-range pointer and wrong ID passed");
    return 0;
}
