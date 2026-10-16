/* SPDX-License-Identifier: BSD-2-Clause */
#include "hash.h"
#include "bearssl_hash.h"
__attribute__((weak)) void rpi5_hash_progress(size_t completed, size_t total)
{
    (void)completed;
    (void)total;
}
int rpi5_sha256(const void *data, size_t length, uint8_t output[32])
{
    if (!output || (length && !data) || length>UINT64_MAX/8) return -1;
    br_sha256_context context;
    br_sha256_init(&context);
    rpi5_hash_progress(0, length);
    size_t completed = 0;
    while (completed < length) {
        size_t chunk = length - completed;
        if (chunk > 256u * 1024u) chunk = 256u * 1024u;
        br_sha256_update(&context, (const uint8_t *)data + completed, chunk);
        completed += chunk;
        rpi5_hash_progress(completed, length);
    }
    br_sha256_out(&context,output);
    return 0;
}
