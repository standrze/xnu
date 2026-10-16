/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate adapter, not yet selected in the kernel build.
 * Transfers state explicitly; no BearSSL context overlays XNU digest storage.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "bearssl_hash.h"
#include "rpi5_sha512_compress.h"

void
rpi5_sha512_compress(uint64_t state[8], size_t nblocks, const void *data)
{
    br_sha512_context ctx;
    unsigned char encoded[64];
    const unsigned char *input = data;
    if (nblocks == 0) {
        return;
    }
    for (size_t i = 0; i < 8; i++) {
        for (size_t j = 0; j < 8; j++) {
            encoded[i * 8 + j] = (unsigned char)(state[i] >> (56 - j * 8));
        }
    }
    br_sha512_init(&ctx);
    br_sha512_set_state(&ctx, encoded, 0);
    /* Compression is independent of the accumulated message length. Feed
     * whole blocks only; the caller owns padding and the total bit count. */
    while (nblocks-- != 0) {
        br_sha512_update(&ctx, input, 128);
        input += 128;
    }
    (void)br_sha512_state(&ctx, encoded);
    for (size_t i = 0; i < 8; i++) {
        uint64_t word = 0;
        for (size_t j = 0; j < 8; j++) {
            word = (word << 8) | encoded[i * 8 + j];
        }
        state[i] = word;
    }
}

/* nbits counts completed blocks, as in XNU's ccdigest context. Its counter is
 * 64-bit; reject overflow rather than silently truncate the SHA-512 length.
 * State and tail are preserved. This helper is not yet a registered callback. */
bool
rpi5_sha512_final_state(const uint64_t state[8], uint64_t nbits,
    const void *tail, size_t tail_len, unsigned char output[64])
{
    unsigned char padded[256] = {0};
    uint64_t final_state[8];
    if (state == NULL || output == NULL || tail_len >= 128 ||
        (tail_len != 0 && tail == NULL) || (nbits % 1024) != 0 ||
        nbits > UINT64_MAX - tail_len * 8) {
        return false;
    }
    memcpy(final_state, state, sizeof final_state);
    if (tail_len) memcpy(padded, tail, tail_len);
    padded[tail_len] = 0x80;
    size_t size = tail_len < 112 ? 128 : 256;
    uint64_t total_bits = nbits + tail_len * 8;
    for (size_t j = 0; j < 8; j++) {
        padded[size - 8 + j] = (unsigned char)(total_bits >> (56 - j * 8));
    }
    rpi5_sha512_compress(final_state, size / 128, padded);
    for (size_t i = 0; i < 64; i++) {
        output[i] = (unsigned char)(final_state[i / 8] >> (56 - (i % 8) * 8));
    }
    return true;
}
