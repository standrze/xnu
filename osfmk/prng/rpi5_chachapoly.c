/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_chachapoly.h"
#include <bearssl_block.h>
#include <corecrypto/ccchacha20poly1305.h>
#include <string.h>
_Static_assert(sizeof(struct rpi5_chachapoly)<=sizeof(ccchacha20poly1305_ctx),"AEAD context fit");
enum { AAD=1, ENCRYPT=2, DECRYPT=3, FINAL=4 };
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
int rpi5_chachapoly_init(struct rpi5_chachapoly *s,const void *key,const void *nonce)
{
    if(!s || !key || !nonce) return -1;
    struct rpi5_chachapoly fresh={0};
    unsigned char mac_key[32]={0};
    (void)rpi5_chacha_stream_init(&fresh.stream,key,nonce);
    (void)br_chacha20_ct_run(key,nonce,0,mac_key,sizeof mac_key);
    rpi5_poly1305_init(&fresh.mac,mac_key);
    fresh.phase=AAD; *s=fresh;
    wipe(mac_key,sizeof mac_key); wipe(&fresh,sizeof fresh);
    return 0;
}
int rpi5_chachapoly_aad(struct rpi5_chachapoly *s,const void *data,size_t n)
{
    if(!s || s->phase!=AAD || (n && !data) || n>UINT64_MAX-s->aad_length ||
        n>UINTPTR_MAX-(uintptr_t)data) return -1;
    rpi5_poly1305_update(&s->mac,data,n); s->aad_length+=n;
    return 0;
}
int rpi5_chachapoly_crypt(struct rpi5_chachapoly *s,const void *in,void *out,size_t n,int encrypt)
{
    uintptr_t a=(uintptr_t)in,b=(uintptr_t)out;
    if(!s || (encrypt!=0 && encrypt!=1)) return -1;
    unsigned phase=encrypt?ENCRYPT:DECRYPT;
    if((s->phase!=AAD && s->phase!=phase) ||
        s->stream.position>RPI5_CHACHA_TEXT_LIMIT ||
        n>RPI5_CHACHA_TEXT_LIMIT-s->stream.position ||
        (n && (!in || !out)) || n>UINTPTR_MAX-a || n>UINTPTR_MAX-b ||
        (in!=out && a<b+n && b<a+n)) return -1;
    if(s->phase==AAD) rpi5_poly1305_pad(&s->mac);
    s->phase=phase;
    if(!encrypt) rpi5_poly1305_update(&s->mac,in,n);
    (void)rpi5_chacha_stream_crypt(&s->stream,n,in,out);
    if(encrypt) rpi5_poly1305_update(&s->mac,out,n);
    return 0;
}
int rpi5_chachapoly_finish(struct rpi5_chachapoly *s,void *tag,int encrypt)
{
    if(!s || !tag || (encrypt!=0 && encrypt!=1) ||
        (s->phase!=AAD && s->phase!=(encrypt?ENCRYPT:DECRYPT))) return -1;
    unsigned char footer[16],computed[16];
    for(unsigned i=0;i<8;i++) {
        footer[i]=(unsigned char)(s->aad_length>>(8*i));
        footer[8+i]=(unsigned char)(s->stream.position>>(8*i));
    }
    rpi5_poly1305_pad(&s->mac);
    rpi5_poly1305_update(&s->mac,footer,16);
    rpi5_poly1305_final(&s->mac,computed);
    volatile unsigned difference=0;
    if(encrypt) memcpy(tag,computed,16);
    else for(unsigned i=0;i<16;i++) difference|=computed[i]^((unsigned char *)tag)[i];
    wipe(computed,sizeof computed); wipe(footer,sizeof footer);
    wipe(s->stream.pad,sizeof s->stream.pad);
    s->phase=FINAL;
    return difference ? -1 : 0;
}
