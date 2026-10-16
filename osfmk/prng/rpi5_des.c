/* SPDX-License-Identifier: BSD-2-Clause
 * Legacy compatibility only; not recommended for new cryptographic uses.
 * The single-DES schedule fits XNU's 256-byte fixed wrapper storage. BearSSL's
 * full context supports 3DES too, so persist subkeys rather than that context.
 */
#include "rpi5_des.h"
#include <corecrypto/cc_error.h>
#include "bearssl_block.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
struct des_state { uint32_t ready,decrypt,triple,skey[96]; };
union des_keys { br_des_ct_cbcenc_keys enc; br_des_ct_cbcdec_keys dec; };
#define DES_READY UINT32_C(0x52444553)
#define DES_SIZE (offsetof(struct des_state,skey)+32*sizeof(uint32_t))
#define TDES_SIZE sizeof(struct des_state)
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static int init(const struct ccmode_ecb *mode,ccecb_ctx *ctx,size_t n,const void *key)
{
    unsigned decrypting,triple;
    if(mode==&rpi5_des_ecb_encrypt) { decrypting=0; triple=0; }
    else if(mode==&rpi5_des_ecb_decrypt) { decrypting=1; triple=0; }
    else if(mode==&rpi5_tdes_ecb_encrypt) { decrypting=0; triple=1; }
    else if(mode==&rpi5_tdes_ecb_decrypt) { decrypting=1; triple=1; }
    else return CCERR_PARAMETER;
    if(!ctx || !key || n!=(triple?24u:8u)) return CCERR_PARAMETER;
    union des_keys keys={0}; struct des_state state={0};
    size_t size=triple?TDES_SIZE:DES_SIZE;
    if(decrypting) {
        br_des_ct_cbcdec_init(&keys.dec,key,n);
        memcpy(state.skey,keys.dec.skey,(triple?96:32)*sizeof(uint32_t));
    } else {
        br_des_ct_cbcenc_init(&keys.enc,key,n);
        memcpy(state.skey,keys.enc.skey,(triple?96:32)*sizeof(uint32_t));
    }
    state.ready=DES_READY; state.decrypt=decrypting; state.triple=triple;
    memcpy(ctx,&state,size); wipe(&keys,sizeof keys); wipe(&state,sizeof state); return 0;
}
static int run(const ccecb_ctx *ctx,size_t blocks,const void *in,void *out,unsigned decrypting,unsigned triple,void *chaining_iv)
{
    if(!ctx || blocks>SIZE_MAX/8) return CCERR_PARAMETER;
    size_t n=blocks*8; uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return CCERR_PARAMETER;
    struct des_state state={0};
    /* Inspect the common header before reading any possibly larger schedule. */
    memcpy(&state,ctx,offsetof(struct des_state,skey));
    if(state.ready!=DES_READY || state.decrypt!=decrypting || state.triple!=triple) {
        wipe(&state,sizeof state); return CCERR_PARAMETER;
    }
    memcpy(&state,ctx,triple?TDES_SIZE:DES_SIZE);
    union des_keys keys={0};
    if(decrypting) {
        keys.dec.vtable=&br_des_ct_cbcdec_vtable; keys.dec.num_rounds=triple?3:1;
        memcpy(keys.dec.skey,state.skey,(triple?96:32)*sizeof(uint32_t));
    } else {
        keys.enc.vtable=&br_des_ct_cbcenc_vtable; keys.enc.num_rounds=triple?3:1;
        memcpy(keys.enc.skey,state.skey,(triple?96:32)*sizeof(uint32_t));
    }
    if(chaining_iv) {
        if(n) {
            if(in!=out) memcpy(out,in,n);
            if(decrypting) br_des_ct_cbcdec_run(&keys.dec,chaining_iv,out,n);
            else br_des_ct_cbcenc_run(&keys.enc,chaining_iv,out,n);
        }
    } else {
      const unsigned char *p=in; unsigned char *q=out;
      for(size_t i=0;i<blocks;i++) {
        unsigned char block[8],iv[8]={0}; memcpy(block,p,8);
        if(decrypting) br_des_ct_cbcdec_run(&keys.dec,iv,block,8);
        else br_des_ct_cbcenc_run(&keys.enc,iv,block,8);
        memcpy(q,block,8); p+=8; q+=8; wipe(block,sizeof block); wipe(iv,sizeof iv);
      }
    }
    wipe(&keys,sizeof keys); wipe(&state,sizeof state); return 0;
}
#define DES_MODE(name,dec,tri,size_) \
static int name##_run(const ccecb_ctx *ctx,size_t n,const void *in,void *out) { return run(ctx,n,in,out,dec,tri,NULL); } \
const struct ccmode_ecb name={.size=size_,.block_size=8,.init=init,.ecb=name##_run}
DES_MODE(rpi5_des_ecb_encrypt,0,0,DES_SIZE);
DES_MODE(rpi5_des_ecb_decrypt,1,0,DES_SIZE);
DES_MODE(rpi5_tdes_ecb_encrypt,0,1,TDES_SIZE);
DES_MODE(rpi5_tdes_ecb_decrypt,1,1,TDES_SIZE);
#undef DES_MODE

static int cbc_init(const struct ccmode_cbc *mode,cccbc_ctx *ctx,size_t n,const void *key)
{
    const struct ccmode_ecb *ecb;
    if(mode==&rpi5_des_cbc_encrypt) ecb=&rpi5_des_ecb_encrypt;
    else if(mode==&rpi5_des_cbc_decrypt) ecb=&rpi5_des_ecb_decrypt;
    else if(mode==&rpi5_tdes_cbc_encrypt) ecb=&rpi5_tdes_ecb_encrypt;
    else if(mode==&rpi5_tdes_cbc_decrypt) ecb=&rpi5_tdes_ecb_decrypt;
    else return CCERR_PARAMETER;
    return init(ecb,(void *)ctx,n,key);
}
/* IV is eight writable bytes disjoint from key and data. No padding. */
#define DES_CBC_MODE(name,dec,tri,size_) \
static int name##_run(const cccbc_ctx *ctx,cccbc_iv *iv,size_t n,const void *in,void *out) { \
    if(!iv) return CCERR_PARAMETER; return run((const void *)ctx,n,in,out,dec,tri,iv); } \
const struct ccmode_cbc name={.size=size_,.block_size=8,.init=cbc_init,.cbc=name##_run}
DES_CBC_MODE(rpi5_des_cbc_encrypt,0,0,DES_SIZE);
DES_CBC_MODE(rpi5_des_cbc_decrypt,1,0,DES_SIZE);
DES_CBC_MODE(rpi5_tdes_cbc_encrypt,0,1,TDES_SIZE);
DES_CBC_MODE(rpi5_tdes_cbc_decrypt,1,1,TDES_SIZE);
#undef DES_CBC_MODE

void rpi5_des_key_set_odd_parity(void *key,unsigned long n)
{
    if(n && !key) __builtin_trap();
    unsigned char *p=key;
    for(unsigned long i=0;i<n;i++) {
        unsigned value=p[i]&0xfeu,parity=0;
        for(unsigned bit=1;bit<8;bit++) parity^=(value>>bit)&1u;
        p[i]=(unsigned char)(value|(parity^1u));
    }
}
int rpi5_des_key_is_weak(void *key,unsigned long n)
{
    if(!key || n!=8) return CCERR_PARAMETER;
    /* Standard four weak and twelve semi-weak effective DES keys. Numeric
     * constants cross-checked against OpenSSL crypto/des/set_key.c. Parity
     * bits do not participate in DES, so this check deliberately ignores them.
     * It does not modify the supplied key. No OpenSSL implementation imported. */
    static const uint64_t weak[16]={
        UINT64_C(0x0101010101010101),UINT64_C(0xfefefefefefefefe),
        UINT64_C(0x1f1f1f1f0e0e0e0e),UINT64_C(0xe0e0e0e0f1f1f1f1),
        UINT64_C(0x01fe01fe01fe01fe),UINT64_C(0xfe01fe01fe01fe01),
        UINT64_C(0x1fe01fe00ef10ef1),UINT64_C(0xe01fe01ff10ef10e),
        UINT64_C(0x01e001e001f101f1),UINT64_C(0xe001e001f101f101),
        UINT64_C(0x1ffe1ffe0efe0efe),UINT64_C(0xfe1ffe1ffe0efe0e),
        UINT64_C(0x011f011f010e010e),UINT64_C(0x1f011f010e010e01),
        UINT64_C(0xe0fee0fef1fef1fe),UINT64_C(0xfee0fee0fef1fef1)
    };
    const unsigned char *p=key; uint64_t value=0;
    for(unsigned i=0;i<8;i++) value=(value<<8)|(p[i]&0xfeu);
    volatile unsigned matches=0;
    for(unsigned i=0;i<16;i++) matches|=(value==(weak[i]&UINT64_C(0xfefefefefefefefe)));
    return (int)matches;
}
