/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate SHA-256 bridge; not selected or registered in the kernel.
 * BearSSL state is serialized explicitly, never overlaid on XNU storage.
 */
#include <corecrypto/ccdigest.h>
#include <string.h>
#include "bearssl_hash.h"
#include "rpi5_digest_abi.h"
extern const struct ccdigest_info rpi5_sha256_di;
static const uint32_t initial[8]={
    0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
static void encode_state(const void *state, unsigned char encoded[32])
{
    uint32_t words[8]; memcpy(words,state,sizeof words);
    for(size_t i=0;i<32;i++) encoded[i]=(unsigned char)(words[i/4]>>(24-(i%4)*8));
}
static void compress(ccdigest_state_t state,size_t blocks,const void *data)
{
    if (!blocks) return;
    if (!data) __builtin_trap();
    unsigned char encoded[32]; uint32_t words[8];
    br_sha256_context hash;
    encode_state(state,encoded);
    br_sha256_init(&hash); br_sha256_set_state(&hash,encoded,0);
    const unsigned char *p=data;
    while(blocks--) { br_sha256_update(&hash,p,64); p+=64; }
    (void)br_sha256_state(&hash,encoded);
    for(size_t i=0;i<8;i++) {
        words[i]=0;
        for(size_t j=0;j<4;j++) words[i]=(words[i]<<8)|encoded[i*4+j];
    }
    memcpy(state,words,sizeof words);
}
static void final(const struct ccdigest_info *di,ccdigest_ctx_t ctx,unsigned char *out)
{
    if(di!=&rpi5_sha256_di || !ctx || !out) __builtin_trap();
    uint64_t bits=rpi5_digest_bits(ctx);
    size_t tail=rpi5_digest_num(di,ctx);
    if(bits%512 || tail>=64 || tail>(UINT64_MAX-bits)/8) __builtin_trap();
    unsigned char encoded[32]; br_sha256_context hash;
    encode_state(rpi5_digest_state(ctx),encoded);
    br_sha256_init(&hash); br_sha256_set_state(&hash,encoded,bits/8);
    br_sha256_update(&hash,ccdigest_data(di,ctx),tail);
    br_sha256_out(&hash,out);
    for(size_t i=0;i<sizeof hash;i++) ((volatile unsigned char *)&hash)[i]=0;
}
const struct ccdigest_info rpi5_sha256_di={
    .output_size=32,.state_size=32,.block_size=64,
    .initial_state=initial,.compress=compress,.final=final};
void rpi5_sha256_digest_init(const struct ccdigest_info *di,ccdigest_ctx_t ctx)
{
    if(di!=&rpi5_sha256_di || !ctx) __builtin_trap();
    memset(ctx,0,ccdigest_di_size(di));
    memcpy(rpi5_digest_state(ctx),initial,sizeof initial);
}
void rpi5_sha256_digest_update(const struct ccdigest_info *di,ccdigest_ctx_t ctx,
    size_t length,const void *data)
{
    if(di!=&rpi5_sha256_di || !ctx || (length && !data)) __builtin_trap();
    size_t buffered=rpi5_digest_num(di,ctx); uint64_t bits=rpi5_digest_bits(ctx);
    if(buffered>=64 || bits%512 || buffered>(UINT64_MAX-bits)/8 ||
        length>(UINT64_MAX-bits)/8-buffered) __builtin_trap();
    const unsigned char *p=data;
    while(length) {
        size_t take=64-buffered; if(take>length) take=length;
        memcpy(ccdigest_data(di,ctx)+buffered,p,take);
        p+=take; length-=take; buffered+=take;
        if(buffered==64) {
            compress(rpi5_digest_state(ctx),1,ccdigest_data(di,ctx));
            bits+=512; buffered=0;
        }
    }
    rpi5_digest_set_bits(ctx,bits); rpi5_digest_set_num(di,ctx,(unsigned)buffered);
}
void rpi5_sha256_digest_final(const struct ccdigest_info *di,ccdigest_ctx_t ctx,void *out)
{
    final(di,ctx,out);
}
void rpi5_sha256_digest(const struct ccdigest_info *di,unsigned long length,
    const void *data,void *out)
{
    if(di!=&rpi5_sha256_di || !out || (length && !data)) __builtin_trap();
    ccdigest_ctx_decl(32,64,ctx);
    rpi5_sha256_digest_init(di,ctx);
    rpi5_sha256_digest_update(di,ctx,length,data);
    final(di,ctx,out);
    for(size_t i=0;i<ccdigest_ctx_size(32,64);i++) ((volatile unsigned char *)ctx)[i]=0;
}
