/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_POLY1305_H
#define RPI5_POLY1305_H
#include <stdint.h>
#include <stddef.h>
struct rpi5_poly1305 { uint32_t r[5],acc[5]; unsigned char s[16],buffer[16]; size_t used; };
/* Internal AEAD primitive: valid pointers, initialized serialized state,
 * disjoint buffers required. pad() ends an AEAD segment with zero padding.
 * final() wipes state; caller appends the AEAD length block first. */
void rpi5_poly1305_init(struct rpi5_poly1305 *,const unsigned char [32]);
void rpi5_poly1305_update(struct rpi5_poly1305 *,const void *,size_t);
void rpi5_poly1305_pad(struct rpi5_poly1305 *);
void rpi5_poly1305_final(struct rpi5_poly1305 *,unsigned char [16]);
#endif
