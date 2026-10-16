/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CHACHAPOLY_H
#define RPI5_CHACHAPOLY_H
#include "rpi5_chacha_stream.h"
#include "rpi5_poly1305.h"
struct rpi5_chachapoly {
    struct rpi5_chacha_stream stream;
    struct rpi5_poly1305 mac;
    uint64_t aad_length;
    unsigned phase;
};
/* Internal candidate. Caller serializes initialized state and keeps all
 * buffers disjoint from it. Decrypted output is unauthenticated until finish
 * succeeds. encrypt must be 0 or 1; finish verifies for 0, generates for 1. */
int rpi5_chachapoly_init(struct rpi5_chachapoly *,const void *,const void *);
int rpi5_chachapoly_aad(struct rpi5_chachapoly *,const void *,size_t);
int rpi5_chachapoly_crypt(struct rpi5_chachapoly *,const void *,void *,size_t,int);
int rpi5_chachapoly_finish(struct rpi5_chachapoly *,void *,int);
#endif
