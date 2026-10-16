/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate AES-ECB compatibility, not registered. BearSSL ct64 primitive;
 * one CBC block with a fresh zero IV is exactly ECB. No padding is performed.
 * Caller supplies descriptor-sized context, disjoint from all buffers. Data
 * may be exactly in place or disjoint; partial overlaps are rejected.
 */
#include "rpi5_aes_ecb.h"
#include <corecrypto/cc_error.h>
#include "bearssl_block.h"
#include <stdint.h>
#include <string.h>
struct aes_key {
    _Alignas(16) union { br_aes_ct64_cbcenc_keys enc; br_aes_ct64_cbcdec_keys dec; } key;
    uint32_t initialized,decrypt;
};
#define AES_KEY_READY UINT32_C(0x52354145)
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static int init(const struct ccmode_ecb *mode,ccecb_ctx *ctx,size_t n,const void *key)
{
    if(!ctx || !key || (n!=16 && n!=24 && n!=32) ||
        (mode!=&rpi5_aes_ecb_encrypt && mode!=&rpi5_aes_ecb_decrypt)) return CCERR_PARAMETER;
    struct aes_key state={0}; state.decrypt=mode==&rpi5_aes_ecb_decrypt;
    if(state.decrypt) br_aes_ct64_cbcdec_init(&state.key.dec,key,n);
    else br_aes_ct64_cbcenc_init(&state.key.enc,key,n);
    state.initialized=AES_KEY_READY;
    memcpy(ctx,&state,sizeof state); wipe(&state,sizeof state); return 0;
}
static int run(const ccecb_ctx *ctx,size_t blocks,const void *in,void *out,unsigned decrypt)
{
    if(!ctx || blocks>SIZE_MAX/16) return CCERR_PARAMETER;
    size_t n=blocks*16; uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return CCERR_PARAMETER;
    struct aes_key state; memcpy(&state,ctx,sizeof state);
    if(state.initialized!=AES_KEY_READY || state.decrypt!=decrypt) {
        wipe(&state,sizeof state); return CCERR_PARAMETER;
    }
    const unsigned char *p=in; unsigned char *q=out;
    for(size_t i=0;i<blocks;i++) {
        unsigned char block[16],iv[16]={0}; memcpy(block,p,16);
        if(decrypt) br_aes_ct64_cbcdec_run(&state.key.dec,iv,block,16);
        else br_aes_ct64_cbcenc_run(&state.key.enc,iv,block,16);
        memcpy(q,block,16); p+=16; q+=16;
        wipe(block,sizeof block); wipe(iv,sizeof iv);
    }
    wipe(&state,sizeof state); return 0;
}
static int encrypt(const ccecb_ctx *ctx,size_t n,const void *in,void *out) { return run(ctx,n,in,out,0); }
static int decrypt(const ccecb_ctx *ctx,size_t n,const void *in,void *out) { return run(ctx,n,in,out,1); }
/* No roundkey callback: not used by the current in-tree consumers; external
 * consumers requiring it remain an explicit compatibility gap. */
const struct ccmode_ecb rpi5_aes_ecb_encrypt={.size=sizeof(struct aes_key),.block_size=16,.init=init,.ecb=encrypt};
const struct ccmode_ecb rpi5_aes_ecb_decrypt={.size=sizeof(struct aes_key),.block_size=16,.init=init,.ecb=decrypt};

static int cbc_init(const struct ccmode_cbc *mode,cccbc_ctx *ctx,size_t n,const void *key)
{
    if(mode==&rpi5_aes_cbc_encrypt) return init(&rpi5_aes_ecb_encrypt,(void *)ctx,n,key);
    if(mode==&rpi5_aes_cbc_decrypt) return init(&rpi5_aes_ecb_decrypt,(void *)ctx,n,key);
    return CCERR_PARAMETER;
}
/* IV points to 16 writable bytes, disjoint from context and both data buffers.
 * CBC runs in place internally. Validate all fallible inputs before copying
 * input or updating IV; on success IV becomes the final ciphertext block.
 */
static int cbc_run(const cccbc_ctx *ctx,cccbc_iv *iv,size_t blocks,const void *in,void *out,unsigned decrypting)
{
    if(!ctx || !iv || blocks>SIZE_MAX/16) return CCERR_PARAMETER;
    size_t n=blocks*16; uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return CCERR_PARAMETER;
    struct aes_key state; memcpy(&state,ctx,sizeof state);
    if(state.initialized!=AES_KEY_READY || state.decrypt!=decrypting) {
        wipe(&state,sizeof state); return CCERR_PARAMETER;
    }
    if(n) {
        if(in!=out) memcpy(out,in,n);
        if(decrypting) br_aes_ct64_cbcdec_run(&state.key.dec,iv,out,n);
        else br_aes_ct64_cbcenc_run(&state.key.enc,iv,out,n);
    }
    wipe(&state,sizeof state); return 0;
}
static int cbc_encrypt(const cccbc_ctx *ctx,cccbc_iv *iv,size_t n,const void *in,void *out)
{
    return cbc_run(ctx,iv,n,in,out,0);
}
static int cbc_decrypt(const cccbc_ctx *ctx,cccbc_iv *iv,size_t n,const void *in,void *out)
{
    return cbc_run(ctx,iv,n,in,out,1);
}
const struct ccmode_cbc rpi5_aes_cbc_encrypt={.size=sizeof(struct aes_key),.block_size=16,.init=cbc_init,.cbc=cbc_encrypt};
const struct ccmode_cbc rpi5_aes_cbc_decrypt={.size=sizeof(struct aes_key),.block_size=16,.init=cbc_init,.cbc=cbc_decrypt};

struct ctr_key { struct aes_key key; unsigned char counter[16],pad[16]; unsigned used; };
static int ctr_init(const struct ccmode_ctr *mode,ccctr_ctx *ctx,size_t n,const void *key,const void *iv)
{
    if(mode!=&rpi5_aes_ctr || !ctx || !iv) return CCERR_PARAMETER;
    struct ctr_key state={0};
    int result=init(&rpi5_aes_ecb_encrypt,(void *)&state.key,n,key);
    if(!result) {
        memcpy(state.counter,iv,16); state.used=16; memcpy(ctx,&state,sizeof state);
    }
    wipe(&state,sizeof state); return result;
}
static int ctr_set(const struct ccmode_ctr *mode,ccctr_ctx *ctx,const void *counter)
{
    if(mode!=&rpi5_aes_ctr || !ctx || !counter) return CCERR_PARAMETER;
    struct ctr_key state; memcpy(&state,ctx,sizeof state);
    if(state.key.initialized!=AES_KEY_READY || state.key.decrypt || state.used>16) {
        wipe(&state,sizeof state); return CCERR_PARAMETER;
    }
    memcpy(state.counter,counter,16); memset(state.pad,0,16); state.used=16;
    memcpy(ctx,&state,sizeof state); wipe(&state,sizeof state); return 0;
}
static int ctr_run(ccctr_ctx *ctx,size_t n,const void *in,void *out)
{
    if(!ctx) return CCERR_PARAMETER;
    uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return CCERR_PARAMETER;
    struct ctr_key state; memcpy(&state,ctx,sizeof state);
    if(state.key.initialized!=AES_KEY_READY || state.key.decrypt || state.used>16) {
        wipe(&state,sizeof state); return CCERR_PARAMETER;
    }
    const unsigned char *p=in; unsigned char *q=out;
    for(size_t i=0;i<n;i++) {
        if(state.used==16) {
            unsigned char iv[16]={0}; memcpy(state.pad,state.counter,16);
            br_aes_ct64_cbcenc_run(&state.key.key.enc,iv,state.pad,16); wipe(iv,sizeof iv);
            /* XNU compatibility: modulo-2^64 big-endian suffix. Prefix is
             * unchanged on wrap; callers must never reuse a key/counter. */
            uint64_t suffix=0;
            for(unsigned j=8;j<16;j++) suffix=(suffix<<8)|state.counter[j];
            suffix++;
            for(unsigned j=0;j<8;j++) state.counter[15-j]=(unsigned char)(suffix>>(j*8));
            state.used=0;
        }
        q[i]=p[i]^state.pad[state.used++];
    }
    memcpy(ctx,&state,sizeof state); wipe(&state,sizeof state); return 0;
}
const struct ccmode_ctr rpi5_aes_ctr={.size=sizeof(struct ctr_key),.block_size=1,.ecb_block_size=16,
    .init=ctr_init,.setctr=ctr_set,.ctr=ctr_run};

struct xts_key { struct aes_key data,tweak; };
struct xts_tweak { unsigned char value[16]; uint32_t ready,blocks; };
#define XTS_TWEAK_READY UINT32_C(0x52585453)
#define XTS_BLOCK_LIMIT (UINT32_C(1)<<20)
static int xts_init(const struct ccmode_xts *mode,ccxts_ctx *ctx,size_t n,const void *data_key,const void *tweak_key)
{
    if(!ctx || !data_key || !tweak_key || (n!=16 && n!=32) ||
        (mode!=&rpi5_aes_xts_encrypt && mode!=&rpi5_aes_xts_decrypt)) return CCERR_PARAMETER;
    const unsigned char *a=data_key,*b=tweak_key; volatile unsigned difference=0;
    for(size_t i=0;i<n;i++) difference|=(unsigned)(a[i]^b[i]);
    if(!difference) return CCERR_PARAMETER;
    struct xts_key state={0};
    const struct ccmode_ecb *data_mode=mode==&rpi5_aes_xts_encrypt?&rpi5_aes_ecb_encrypt:&rpi5_aes_ecb_decrypt;
    int result=init(data_mode,(void *)&state.data,n,data_key);
    if(!result) result=init(&rpi5_aes_ecb_encrypt,(void *)&state.tweak,n,tweak_key);
    if(!result) memcpy(ctx,&state,sizeof state);
    wipe(&state,sizeof state); return result;
}
static void xts_schedule(const struct ccmode_xts *mode,ccxts_ctx *ctx,size_t n,const void *key,const void *tweak_key)
{
    if(xts_init(mode,ctx,n,key,tweak_key)) __builtin_trap();
}
static int xts_set(const ccxts_ctx *ctx,ccxts_tweak *tweak,const void *iv)
{
    if(!ctx || !tweak || !iv) return CCERR_PARAMETER;
    struct xts_key key; memcpy(&key,ctx,sizeof key);
    if(key.data.initialized!=AES_KEY_READY || key.tweak.initialized!=AES_KEY_READY ||
        key.data.decrypt>1 || key.tweak.decrypt) { wipe(&key,sizeof key); return CCERR_PARAMETER; }
    struct xts_tweak state={0};
    int result=encrypt((const void *)&key.tweak,1,iv,state.value);
    if(!result) { state.ready=XTS_TWEAK_READY; memcpy(tweak,&state,sizeof state); }
    wipe(&state,sizeof state); wipe(&key,sizeof key); return result;
}
/* Full blocks only, as required by the local libkern wrappers. No ciphertext
 * stealing here. Key, tweak and data storage must be mutually disjoint except
 * for exact in-place input/output. Rejections preserve tweak and output. */
static void *xts_run(const ccxts_ctx *ctx,ccxts_tweak *tweak,size_t blocks,const void *in,void *out,unsigned decrypting)
{
    if(!ctx || !tweak || blocks>XTS_BLOCK_LIMIT) return NULL;
    size_t n=blocks*16; uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return NULL;
    struct xts_key key; struct xts_tweak state;
    memcpy(&key,ctx,sizeof key); memcpy(&state,tweak,sizeof state);
    if(key.data.initialized!=AES_KEY_READY || key.data.decrypt!=decrypting ||
        state.ready!=XTS_TWEAK_READY || state.blocks>XTS_BLOCK_LIMIT || blocks>XTS_BLOCK_LIMIT-state.blocks) {
        wipe(&key,sizeof key); wipe(&state,sizeof state); return NULL;
    }
    const unsigned char *p=in; unsigned char *q=out;
    for(size_t i=0;i<blocks;i++) {
        unsigned char block[16],iv[16]={0};
        for(unsigned j=0;j<16;j++) block[j]=p[j]^state.value[j];
        if(decrypting) br_aes_ct64_cbcdec_run(&key.data.key.dec,iv,block,16);
        else br_aes_ct64_cbcenc_run(&key.data.key.enc,iv,block,16);
        for(unsigned j=0;j<16;j++) q[j]=block[j]^state.value[j];
        unsigned carry=0;
        for(unsigned j=0;j<16;j++) {
            unsigned value=state.value[j];
            state.value[j]=(unsigned char)((value<<1)|carry); carry=value>>7;
        }
        state.value[0]^=(unsigned char)(0x87u & (0u-carry));
        p+=16; q+=16; state.blocks++;
        wipe(block,sizeof block); wipe(iv,sizeof iv);
    }
    memcpy(tweak,&state,sizeof state); wipe(&key,sizeof key); wipe(&state,sizeof state); return tweak;
}
static void *xts_encrypt_blocks(const ccxts_ctx *c,ccxts_tweak *t,size_t n,const void *i,void *o) { return xts_run(c,t,n,i,o,0); }
static void *xts_decrypt_blocks(const ccxts_ctx *c,ccxts_tweak *t,size_t n,const void *i,void *o) { return xts_run(c,t,n,i,o,1); }
const struct ccmode_xts rpi5_aes_xts_encrypt={.size=sizeof(struct xts_key),.tweak_size=sizeof(struct xts_tweak),
    .block_size=16,.init=xts_init,.key_sched=xts_schedule,.set_tweak=xts_set,.xts=xts_encrypt_blocks};
const struct ccmode_xts rpi5_aes_xts_decrypt={.size=sizeof(struct xts_key),.tweak_size=sizeof(struct xts_tweak),
    .block_size=16,.init=xts_init,.key_sched=xts_schedule,.set_tweak=xts_set,.xts=xts_decrypt_blocks};
