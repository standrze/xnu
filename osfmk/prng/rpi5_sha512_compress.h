/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SHA512_COMPRESS_H
#define RPI5_SHA512_COMPRESS_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
void rpi5_sha512_compress(uint64_t state[8],size_t,const void *);
bool rpi5_sha512_final_state(const uint64_t state[8],uint64_t,const void *,size_t,unsigned char output[64]);
#endif
