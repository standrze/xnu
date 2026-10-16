/* SPDX-License-Identifier: BSD-2-Clause
 * MD5/SHA-1 compatibility for existing XNU interfaces, not new security uses.
 * Explicit serialized-state bridge to pinned BearSSL. Not registered yet.
 */
#include "rpi5_digest_abi.h"
#include "bearssl_hash.h"
static const uint32_t md5_initial[4]={0x67452301,0xefcdab89,0x98badcfe,0x10325476};
static const uint32_t sha1_initial[5]={0x67452301,0xefcdab89,0x98badcfe,0x10325476,0xc3d2e1f0};
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static const br_hash_class *algorithm(const struct ccdigest_info *di)
{
    if(di==&rpi5_md5_di) return &br_md5_vtable;
    if(di==&rpi5_sha1_di) return &br_sha1_vtable;
    __builtin_trap();
}
static void encode(const struct ccdigest_info *di,const void *state,unsigned char out[20])
{
    uint32_t words[5]={0}; memcpy(words,state,di->state_size);
    for(size_t i=0;i<di->state_size;i++) {
        unsigned shift=(unsigned)(di==&rpi5_md5_di ? i%4 : 3-i%4)*8;
        out[i]=(unsigned char)(words[i/4]>>shift);
    }
    wipe(words,sizeof words);
}
static void compress(const struct ccdigest_info *di,void *state,size_t blocks,const void *data)
{
    if(!blocks) return;
    if(!state || !data) __builtin_trap();
    const br_hash_class *alg=algorithm(di);
    br_hash_compat_context hash;
    unsigned char encoded[20]; uint32_t words[5]={0};
    encode(di,state,encoded); alg->init(&hash.vtable);
    alg->set_state(&hash.vtable,encoded,0);
    const unsigned char *p=data;
    while(blocks--) { alg->update(&hash.vtable,p,64); p+=64; }
    (void)alg->state(&hash.vtable,encoded);
    for(size_t i=0;i<di->state_size;i++) {
        unsigned shift=(unsigned)(di==&rpi5_md5_di ? i%4 : 3-i%4)*8;
        words[i/4]|=(uint32_t)encoded[i]<<shift;
    }
    memcpy(state,words,di->state_size);
    wipe(&hash,sizeof hash); wipe(encoded,sizeof encoded); wipe(words,sizeof words);
}
static void md5_compress(ccdigest_state_t s,size_t n,const void *p) { compress(&rpi5_md5_di,s,n,p); }
static void sha1_compress(ccdigest_state_t s,size_t n,const void *p) { compress(&rpi5_sha1_di,s,n,p); }
static void final(const struct ccdigest_info *di,ccdigest_ctx_t ctx,unsigned char *out)
{
    const br_hash_class *alg=algorithm(di);
    if(!ctx || !out) __builtin_trap();
    uint64_t bits=rpi5_digest_bits(ctx); size_t tail=rpi5_digest_num(di,ctx);
    if(bits%512 || tail>=64 || tail>(UINT64_MAX-bits)/8) __builtin_trap();
    br_hash_compat_context hash; unsigned char encoded[20];
    encode(di,rpi5_digest_state(ctx),encoded);
    alg->init(&hash.vtable); alg->set_state(&hash.vtable,encoded,bits/8);
    alg->update(&hash.vtable,ccdigest_data(di,ctx),tail); alg->out(&hash.vtable,out);
    wipe(&hash,sizeof hash); wipe(encoded,sizeof encoded);
}
const struct ccdigest_info rpi5_md5_di={
    .output_size=16,.state_size=16,.block_size=64,
    .initial_state=md5_initial,.compress=md5_compress,.final=final};
const struct ccdigest_info rpi5_sha1_di={
    .output_size=20,.state_size=20,.block_size=64,
    .initial_state=sha1_initial,.compress=sha1_compress,.final=final};
void rpi5_legacy_digest_init(const struct ccdigest_info *di,ccdigest_ctx_t ctx)
{
    (void)algorithm(di); if(!ctx) __builtin_trap();
    memset(ctx,0,ccdigest_di_size(di));
    memcpy(rpi5_digest_state(ctx),di->initial_state,di->state_size);
}
void rpi5_legacy_digest_update(const struct ccdigest_info *di,ccdigest_ctx_t ctx,size_t n,const void *data)
{
    (void)algorithm(di); if(!ctx || (n && !data)) __builtin_trap();
    uint64_t bits=rpi5_digest_bits(ctx); size_t buffered=rpi5_digest_num(di,ctx);
    if(bits%512 || buffered>=64 || buffered>(UINT64_MAX-bits)/8 ||
        n>(UINT64_MAX-bits)/8-buffered) __builtin_trap();
    const unsigned char *p=data;
    while(n) {
        size_t take=64-buffered; if(take>n) take=n;
        memcpy(ccdigest_data(di,ctx)+buffered,p,take);
        p+=take; n-=take; buffered+=take;
        if(buffered==64) { di->compress(rpi5_digest_state(ctx),1,ccdigest_data(di,ctx)); bits+=512; buffered=0; }
    }
    rpi5_digest_set_bits(ctx,bits); rpi5_digest_set_num(di,ctx,(unsigned)buffered);
}
void rpi5_legacy_digest_final(const struct ccdigest_info *di,ccdigest_ctx_t ctx,void *out) { final(di,ctx,out); }
void rpi5_legacy_digest(const struct ccdigest_info *di,unsigned long n,const void *data,void *out)
{
    (void)algorithm(di); if(!out || (n && !data)) __builtin_trap();
    ccdigest_ctx_decl(20,64,ctx);
    rpi5_legacy_digest_init(di,ctx); rpi5_legacy_digest_update(di,ctx,n,data); final(di,ctx,out);
    wipe(ctx,ccdigest_ctx_size(20,64));
}
