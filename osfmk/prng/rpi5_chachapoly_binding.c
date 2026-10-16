/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_chachapoly_binding.h"
#include "rpi5_chachapoly.h"
#include <corecrypto/cc_error.h>
#include <string.h>
struct binding { struct rpi5_chachapoly core; uint64_t magic; };
#define MAGIC UINT64_C(0x7270693561656164)
_Static_assert(sizeof(struct binding)<=sizeof(ccchacha20poly1305_ctx),"binding size");
static const struct ccchacha20poly1305_info descriptor={};
static const struct ccchacha20poly1305_info *info(void) { return &descriptor; }
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static int args(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c) {
    return i==&descriptor && c;
}
static int buffer(ccchacha20poly1305_ctx *c,const void *p,size_t n) {
    uintptr_t a=(uintptr_t)c,b=(uintptr_t)p;
    return (!n || p) && n<=UINTPTR_MAX-b &&
        (!n || b>=a+sizeof *c || b+n<=a);
}
static int load(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,struct binding *b) {
    if(!args(i,c)) return 0;
    memcpy(b,c,sizeof *b);
    if(b->magic==MAGIC && b->core.phase<=4 && b->core.mac.used<16 &&
        b->core.stream.position<=RPI5_CHACHA_TEXT_LIMIT) return 1;
    wipe(b,sizeof *b); return 0;
}
static int save(ccchacha20poly1305_ctx *c,struct binding *b,int result) {
    if(!result) memcpy(c,b,sizeof *b);
    wipe(b,sizeof *b); return result?CCERR_PARAMETER:0;
}
static int init(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,const uint8_t *key) {
    if(!args(i,c) || !buffer(c,key,32)) return CCERR_PARAMETER;
    struct binding b={0}; b.magic=MAGIC;
    memcpy(b.core.stream.key,key,32);
    memset(c,0,sizeof *c); return save(c,&b,0);
}
static int reset(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c) {
    struct binding b;
    if(!load(i,c,&b)) return CCERR_PARAMETER;
    wipe(&b.core.mac,sizeof b.core.mac);
    wipe(b.core.stream.pad,sizeof b.core.stream.pad);
    b.core.stream.position=0; b.core.aad_length=0; b.core.phase=0;
    return save(c,&b,0);
}
static int setnonce(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,const uint8_t *nonce) {
    struct binding b;
    if(!buffer(c,nonce,12) || !load(i,c,&b)) return CCERR_PARAMETER;
    int result=b.core.phase? -1:rpi5_chachapoly_init(&b.core,b.core.stream.key,nonce);
    return save(c,&b,result);
}
static int aad(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,size_t n,const void *p) {
    struct binding b;
    if(!buffer(c,p,n) || !load(i,c,&b)) return CCERR_PARAMETER;
    return save(c,&b,rpi5_chachapoly_aad(&b.core,p,n));
}
static int crypt(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,size_t n,const void *in,void *out,int encrypt) {
    struct binding b;
    if(!buffer(c,in,n) || !buffer(c,out,n) || !load(i,c,&b)) return CCERR_PARAMETER;
    return save(c,&b,rpi5_chachapoly_crypt(&b.core,in,out,n,encrypt));
}
static int enc(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,size_t n,const void *in,void *out) { return crypt(i,c,n,in,out,1); }
static int dec(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,size_t n,const void *in,void *out) { return crypt(i,c,n,in,out,0); }
static int finalize(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,uint8_t *tag) {
    struct binding b;
    if(!buffer(c,tag,16) || !load(i,c,&b)) return CCERR_PARAMETER;
    return save(c,&b,rpi5_chachapoly_finish(&b.core,tag,1));
}
static int verify(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,const uint8_t *tag) {
    struct binding b; unsigned char expected[16];
    if(!buffer(c,tag,16) || !load(i,c,&b)) return CCERR_PARAMETER;
    if(b.core.phase!=1 && b.core.phase!=3) return save(c,&b,-1);
    memcpy(expected,tag,16);
    int result=rpi5_chachapoly_finish(&b.core,expected,0);
    wipe(expected,sizeof expected);
    (void)save(c,&b,0); /* Failed authentication also consumes the message. */
    return result?CCERR_INTEGRITY:0;
}
static int incnonce(const struct ccchacha20poly1305_info *i,ccchacha20poly1305_ctx *c,uint8_t *nonce) {
    /* Apple source blob 96e59142ea805fc98b297b83dbd9c20dd502486e exposes
     * this operation but does not implement it. Do not invent nonce policy. */
    (void)i; (void)c; (void)nonce;
    return 1;
}
const struct ccchacha20poly1305_fns rpi5_chachapoly_functions={
    .info=info,.init=init,.reset=reset,.setnonce=setnonce,.incnonce=incnonce,
    .aad=aad,.encrypt=enc,.decrypt=dec,.finalize=finalize,.verify=verify
};
