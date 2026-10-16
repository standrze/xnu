/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CHACHA_STREAM_H
#define RPI5_CHACHA_STREAM_H
#include <stdint.h>
#include <stddef.h>
#define RPI5_CHACHA_TEXT_LIMIT ((UINT64_C(1)<<38)-64)
struct rpi5_chacha_stream {
    uint8_t key[32],nonce[12],pad[64];
    uint64_t position;
};
/* Internal AEAD text stream: starts at counter one. Caller initializes and
 * serializes state, keeps buffers disjoint from it and never reuses nonces.
 * This helper alone provides no authentication. */
int rpi5_chacha_stream_init(struct rpi5_chacha_stream *,const void *,const void *);
int rpi5_chacha_stream_crypt(struct rpi5_chacha_stream *,size_t,const void *,void *);
#endif
