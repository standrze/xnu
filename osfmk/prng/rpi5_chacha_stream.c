/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_chacha_stream.h"
#include <bearssl_block.h>
#include <string.h>
int rpi5_chacha_stream_init(struct rpi5_chacha_stream *s,const void *key,const void *nonce)
{
    if(!s || !key || !nonce) return -1;
    struct rpi5_chacha_stream initial={0};
    memcpy(initial.key,key,32); memcpy(initial.nonce,nonce,12);
    *s=initial;
    volatile unsigned char *p=(void *)&initial;
    for(size_t i=0;i<sizeof initial;i++) p[i]=0;
    return 0;
}
int rpi5_chacha_stream_crypt(struct rpi5_chacha_stream *s,size_t n,const void *in,void *out)
{
    uintptr_t a=(uintptr_t)in,b=(uintptr_t)out;
    if(!s || s->position>RPI5_CHACHA_TEXT_LIMIT ||
        n>RPI5_CHACHA_TEXT_LIMIT-s->position ||
        (n && (!in || !out)) || n>UINTPTR_MAX-a || n>UINTPTR_MAX-b ||
        (in!=out && a<b+n && b<a+n)) return -1;
    const unsigned char *input=in; unsigned char *output=out;
    while(n) {
        size_t used=(size_t)(s->position%64);
        if(!used) {
            memset(s->pad,0,sizeof s->pad);
            (void)br_chacha20_ct_run(s->key,s->nonce,
                (uint32_t)(s->position/64+1),s->pad,sizeof s->pad);
        }
        size_t take=64-used; if(take>n) take=n;
        for(size_t i=0;i<take;i++) output[i]=input[i]^s->pad[used+i];
        s->position+=take; n-=take; input+=take; output+=take;
    }
    return 0;
}
