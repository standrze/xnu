/* SPDX-License-Identifier: BSD-2-Clause
 * Host-only probe. Vector values are from BearSSL's MIT-licensed test_crypto.c;
 * Copyright (c) 2016 Thomas Pornin. See accompanying BearSSL-LICENSE.txt.
 * This does not test entropy quality or a kernel provider adapter.
 */
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <libkern/crypto/sha2.h>
#include <libkern/crypto/register_crypto.h>
#include "bearssl.h"
#include <corecrypto/ccdigest.h>
extern const struct ccdigest_info rpi5_sha512_di;
extern const struct ccdigest_info rpi5_sha384_di;
extern const struct ccdigest_info rpi5_sha256_di;
void rpi5_digest_init(const struct ccdigest_info *, ccdigest_ctx_t);
void rpi5_digest_update(const struct ccdigest_info *, ccdigest_ctx_t, size_t, const void *);
void rpi5_digest_final(const struct ccdigest_info *, ccdigest_ctx_t, void *);
void rpi5_digest(const struct ccdigest_info *, unsigned long, const void *, void *);
void rpi5_sha512_digest_init(const struct ccdigest_info *, ccdigest_ctx_t);
void rpi5_sha512_digest_update(const struct ccdigest_info *, ccdigest_ctx_t, size_t, const void *);
void rpi5_sha512_digest_final(const struct ccdigest_info *, ccdigest_ctx_t, void *);
void rpi5_sha512_digest(const struct ccdigest_info *, unsigned long, const void *, void *);
void rpi5_sha512_compress(uint64_t state[8], size_t nblocks, const void *data);
bool rpi5_sha512_final_state(const uint64_t state[8], uint64_t nbits,
    const void *tail, size_t tail_len, unsigned char output[64]);

/* Host-only fixture, never passed to register_crypto or linked into XNU. */
static struct crypto_functions fixture = {
    .ccsha512_di = &rpi5_sha512_di,
    .ccsha384_di = &rpi5_sha384_di,
    .ccsha256_di = &rpi5_sha256_di,
    .ccdigest_init_fn = rpi5_digest_init,
    .ccdigest_update_fn = rpi5_digest_update,
    .ccdigest_final_fn = rpi5_digest_final,
    .ccdigest_fn = rpi5_digest,
};
struct crypto_functions *g_crypto_funcs = &fixture;
void panic(const char *message, ...) __attribute__((noreturn));
void panic(const char *message, ...) { fputs(message, stderr); __builtin_trap(); }

int main(void)
{
    {
        uint64_t state[8];
        unsigned char initial[64], reference[64], block[256];
        br_sha512_context hash;
        for (size_t i = 0; i < sizeof block; i++) block[i] = (unsigned char)i;
        br_sha512_init(&hash);
        (void)br_sha512_state(&hash, initial);
        for (size_t i = 0; i < 8; i++) {
            state[i] = 0;
            for (size_t j = 0; j < 8; j++) state[i] = (state[i] << 8) | initial[i * 8 + j];
        }
        rpi5_sha512_compress(state, 0, NULL);
        rpi5_sha512_compress(state, 1, block);
        rpi5_sha512_compress(state, 1, block + 128);
        br_sha512_update(&hash, block, sizeof block);
        (void)br_sha512_state(&hash, reference);
        for (size_t i = 0; i < 64; i++) {
            if ((unsigned char)(state[i / 8] >> (56 - (i % 8) * 8)) != reference[i]) return 2;
        }
        puts("Compression bridge passed");
    }
    static const unsigned char seed[] = {
        0x00,0x9a,0x4d,0x67,0x92,0x29,0x5a,0x7f,0x73,0x0f,0xc3,0xf2,0xb4,0x9c,
        0xbc,0x0f,0x62,0xe8,0x62,0x27,0x2f,0x01,0x79,0x5e,0xdf,0x0d,0x54,0xdb,
        0x76,0x0f,0x15,0x6d,0x0d,0xac,0x04,0xc0,0x32,0x2b,0x3a,0x20,0x42,0x24
    };
    static const unsigned char expected[] = {
        0x93,0x05,0xa4,0x6d,0xe7,0xff,0x8e,0xb1,0x07,0x19,0x4d,0xeb,0xd3,0xfd,
        0x48,0xaa,0x20,0xd5,0xe7,0x65,0x6c,0xbe,0x0e,0xa6,0x9d,0x2a,0x8d,0x4e,0x7c,0x67
    };
    br_hmac_drbg_context ctx;
    unsigned char output[sizeof expected];
    br_hmac_drbg_init(&ctx, &br_sha256_vtable, seed, sizeof seed);
    br_hmac_drbg_generate(&ctx, output, sizeof output);
    if (memcmp(output, expected, sizeof output)) {
        fputs("HMAC_DRBG subset KAT failed\n", stderr);
        return 1;
    }
    puts("HMAC_DRBG subset KAT passed");
    {
        static const size_t lengths[] = {0, 1, 111, 112, 127, 128, 129, 255, 256, 257};
        unsigned char data[257], digest[64];
        for (size_t i = 0; i < sizeof data; i++) data[i] = (unsigned char)i;
        for (size_t n = 0; n < sizeof lengths / sizeof lengths[0]; n++) {
            br_sha512_context hash;
            br_sha512_init(&hash);
            /* Byte-wise updates exercise buffered input across block boundaries. */
            for (size_t i = 0; i < lengths[n]; i++) br_sha512_update(&hash, data + i, 1);
            br_sha512_out(&hash, digest);
            {
                br_sha512_context initial;
                unsigned char encoded[64], adapted[64];
                uint64_t state[8];
                br_sha512_init(&initial);
                (void)br_sha512_state(&initial, encoded);
                for (size_t i = 0; i < 8; i++) {
                    state[i] = 0;
                    for (size_t j = 0; j < 8; j++) state[i] = (state[i] << 8) | encoded[i * 8 + j];
                }
                size_t blocks = lengths[n] / 128;
                rpi5_sha512_compress(state, blocks, data);
                if (!rpi5_sha512_final_state(state, blocks * 1024,
                    data + blocks * 128, lengths[n] % 128, adapted)) return 3;
                if (memcmp(adapted, digest, 64)) return 4;
                if (rpi5_sha512_final_state(state, 1, NULL, 0, adapted)) return 5;
                if (rpi5_sha512_final_state(state, 0, data, 128, adapted)) return 6;
                {
                    const struct ccdigest_info *di = &rpi5_sha512_di;
                    fixture.ccdigest_fn(di,lengths[n],data,adapted);
                    if (memcmp(adapted,digest,64)) return 11;
                    ccdigest_ctx_decl(64, 128, ccctx);
                    memcpy(ccdigest_state(di, ccctx), di->initial_state, 64);
                    ccdigest_nbits(di, ccctx) = blocks * 1024;
                    ccdigest_num(di, ccctx) = lengths[n] % 128;
                    memcpy(ccdigest_data(di, ccctx), data + blocks * 128, lengths[n] % 128);
                    di->compress(ccdigest_state(di, ccctx), blocks, data);
                    ccdigest_final(di, ccctx, adapted);
                    if (memcmp(adapted, digest, 64)) return 7;
                    for (size_t chunk = 1; chunk <= 129; chunk++) {
                        struct { uint64_t before[2]; SHA512_CTX ctx; uint64_t after[2]; } guarded;
                        memset(&guarded, 0xa5, sizeof guarded);
                        SHA512_Init(&guarded.ctx);
                        SHA512_Update(&guarded.ctx, NULL, 0);
                        rpi5_sha512_digest_init(di, ccctx);
                        rpi5_sha512_digest_update(di, ccctx, 0, NULL);
                        for (size_t offset = 0; offset < lengths[n];) {
                            size_t take = lengths[n] - offset;
                            if (take > chunk) take = chunk;
                            rpi5_sha512_digest_update(di, ccctx, take, data + offset);
                            SHA512_Update(&guarded.ctx, data + offset, take);
                            offset += take;
                        }
                        ccdigest_final(di, ccctx, adapted);
                        if (memcmp(adapted, digest, 64)) return 8;
                        fixture.ccdigest_final_fn(di, ccctx, adapted);
                        if (memcmp(adapted, digest, 64)) return 12;
                        SHA512_Final(adapted, &guarded.ctx);
                        if (memcmp(adapted, digest, 64)) return 9;
                        for (size_t i = 0; i < 2; i++) {
                            if (guarded.before[i] != UINT64_C(0xa5a5a5a5a5a5a5a5) ||
                                guarded.after[i] != UINT64_C(0xa5a5a5a5a5a5a5a5)) return 10;
                        }
                    }
                }
            }
            printf("SHA512 %zu ", lengths[n]);
            for (size_t i = 0; i < sizeof digest; i++) printf("%02x", digest[i]);
            putchar('\n');
        }
    }
    puts("XNU SHA512 wrappers passed: 1290 chunk/boundary cases with context canaries");
    {
        const size_t lengths[]={0,1,111,112,127,128,129,255,256,257};
        unsigned char data[257], expected384[48], guarded[50];
        for(size_t i=0;i<sizeof data;i++) data[i]=(unsigned char)i;
        for(size_t n=0;n<sizeof lengths/sizeof lengths[0];n++) {
            br_sha384_context reference;
            br_sha384_init(&reference);
            br_sha384_update(&reference,data,lengths[n]);
            br_sha384_out(&reference,expected384);
            const struct ccdigest_info *di=&rpi5_sha384_di;
            memset(guarded,0xa5,sizeof guarded);
            fixture.ccdigest_fn(di,lengths[n],lengths[n]?data:NULL,guarded+1);
            if(memcmp(guarded+1,expected384,48) || guarded[0]!=0xa5 || guarded[49]!=0xa5) return 13;
            for(size_t chunk=1;chunk<=129;chunk++) {
                struct { uint64_t before[2]; SHA384_CTX ctx; uint64_t after[2]; } wrapper;
                memset(&wrapper,0xa5,sizeof wrapper);
                SHA384_Init(&wrapper.ctx);
                SHA384_Update(&wrapper.ctx,NULL,0);
                ccdigest_ctx_decl(64,128,ctx384);
                fixture.ccdigest_init_fn(di,ctx384);
                fixture.ccdigest_update_fn(di,ctx384,0,NULL);
                for(size_t offset=0;offset<lengths[n];) {
                    size_t take=lengths[n]-offset;
                    if(take>chunk) take=chunk;
                    fixture.ccdigest_update_fn(di,ctx384,take,data+offset);
                    SHA384_Update(&wrapper.ctx,data+offset,take);
                    offset+=take;
                }
                fixture.ccdigest_final_fn(di,ctx384,guarded+1);
                if(memcmp(guarded+1,expected384,48) || guarded[0]!=0xa5 || guarded[49]!=0xa5) return 14;
                SHA384_Final(guarded+1,&wrapper.ctx);
                if(memcmp(guarded+1,expected384,48) || guarded[0]!=0xa5 || guarded[49]!=0xa5) return 15;
                for(size_t i=0;i<2;i++)
                    if(wrapper.before[i]!=UINT64_C(0xa5a5a5a5a5a5a5a5) ||
                        wrapper.after[i]!=UINT64_C(0xa5a5a5a5a5a5a5a5)) return 16;
            }
            printf("SHA384 %zu ",lengths[n]);
            for(size_t i=0;i<48;i++) printf("%02x",guarded[i+1]);
            putchar('\n');
        }
    }
    puts("XNU SHA384 wrappers passed: 1290 chunk/boundary cases with context/output canaries");
    {
        const size_t lengths[]={0,1,55,56,63,64,65,127,128,129,255,256,257};
        unsigned char data[257],reference[32],out[34];
        for(size_t i=0;i<sizeof data;i++) data[i]=(unsigned char)i;
        for(size_t n=0;n<sizeof lengths/sizeof lengths[0];n++) {
            br_sha256_context hash;
            br_sha256_init(&hash); br_sha256_update(&hash,data,lengths[n]);
            br_sha256_out(&hash,reference);
            memset(out,0xa5,sizeof out);
            fixture.ccdigest_fn(&rpi5_sha256_di,lengths[n],data,out+1);
            if(memcmp(out+1,reference,32) || out[0]!=0xa5 || out[33]!=0xa5) return 17;
            for(size_t chunk=1;chunk<=65;chunk++) {
                struct { uint64_t before[2]; SHA256_CTX ctx; uint64_t after[2]; } wrapper;
                memset(&wrapper,0xa5,sizeof wrapper);
                SHA256_Init(&wrapper.ctx); SHA256_Update(&wrapper.ctx,NULL,0);
                for(size_t offset=0;offset<lengths[n];) {
                    size_t take=lengths[n]-offset; if(take>chunk) take=chunk;
                    SHA256_Update(&wrapper.ctx,data+offset,take); offset+=take;
                }
                SHA256_Final(out+1,&wrapper.ctx);
                if(memcmp(out+1,reference,32) || out[0]!=0xa5 || out[33]!=0xa5) return 18;
                for(size_t i=0;i<2;i++)
                    if(wrapper.before[i]!=UINT64_C(0xa5a5a5a5a5a5a5a5) ||
                        wrapper.after[i]!=UINT64_C(0xa5a5a5a5a5a5a5a5)) return 19;
            }
            printf("SHA256 %zu ",lengths[n]);
            for(size_t i=0;i<32;i++) printf("%02x",out[i+1]);
            putchar('\n');
        }
    }
    return 0;
}
