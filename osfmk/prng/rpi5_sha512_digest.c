/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate SHA-512/SHA-384 descriptors for the pinned XNU digest ABI.
 * Not registered as a complete crypto provider and not selected by the build.
 */
#include <corecrypto/ccdigest.h>
#include <stdbool.h>
#include <string.h>
#include "rpi5_digest_abi.h"

#include "rpi5_sha512_compress.h"

static const uint64_t initial_state[8] = {
    UINT64_C(0x6a09e667f3bcc908), UINT64_C(0xbb67ae8584caa73b),
    UINT64_C(0x3c6ef372fe94f82b), UINT64_C(0xa54ff53a5f1d36f1),
    UINT64_C(0x510e527fade682d1), UINT64_C(0x9b05688c2b3e6c1f),
    UINT64_C(0x1f83d9abfb41bd6b), UINT64_C(0x5be0cd19137e2179),
};
/* SHA-384 algorithm initialization constants (not truncated SHA-512). */
static const uint64_t initial_state384[8] = {
    UINT64_C(0xcbbb9d5dc1059ed8), UINT64_C(0x629a292a367cd507),
    UINT64_C(0x9159015a3070dd17), UINT64_C(0x152fecd8f70e5939),
    UINT64_C(0x67332667ffc00b31), UINT64_C(0x8eb44a8768581511),
    UINT64_C(0xdb0c2e0d64f98fa7), UINT64_C(0x47b5481dbefa4fa4),
};
extern const struct ccdigest_info rpi5_sha512_di, rpi5_sha384_di;
static bool supported(const struct ccdigest_info *di)
{
    return di == &rpi5_sha512_di || di == &rpi5_sha384_di;
}

static void
compress_state(ccdigest_state_t state, size_t blocks, const void *data)
{
    uint64_t words[8];
    memcpy(words, state, sizeof words);
    rpi5_sha512_compress(words, blocks, data);
    memcpy(state, words, sizeof words);
}

static void
final_digest(const struct ccdigest_info *di, ccdigest_ctx_t ctx, unsigned char *out)
{
    uint64_t words[8];
    unsigned char full[64];
    if (!supported(di) || ctx == NULL || out == NULL) {
        __builtin_trap();
    }
    memcpy(words, rpi5_digest_state(ctx), sizeof words);
    if (!rpi5_sha512_final_state(words, rpi5_digest_bits(ctx),
        ccdigest_data(di, ctx), rpi5_digest_num(di, ctx), full)) {
        __builtin_trap();
    }
    memcpy(out, full, di->output_size);
    for (size_t i=0;i<sizeof full;i++) ((volatile unsigned char *)full)[i]=0;
}

const struct ccdigest_info rpi5_sha512_di = {
    .output_size = 64, .state_size = 64, .block_size = 128,
    .initial_state = initial_state, .compress = compress_state, .final = final_digest,
};
const struct ccdigest_info rpi5_sha384_di = {
    .output_size = 48, .state_size = 64, .block_size = 128,
    .initial_state = initial_state384, .compress = compress_state, .final = final_digest,
};

void
rpi5_sha512_digest_init(const struct ccdigest_info *di, ccdigest_ctx_t ctx)
{
    if (!supported(di) || ctx == NULL) __builtin_trap();
    memset(ctx, 0, ccdigest_di_size(di));
    memcpy(rpi5_digest_state(ctx), di->initial_state, sizeof initial_state);
}

void
rpi5_sha512_digest_update(const struct ccdigest_info *di, ccdigest_ctx_t ctx,
    size_t length, const void *data)
{
    if (!supported(di) || ctx == NULL || (length && data == NULL)) __builtin_trap();
    size_t buffered = rpi5_digest_num(di, ctx);
    uint64_t bits = rpi5_digest_bits(ctx);
    if (buffered >= 128 || bits % 1024 ||
        buffered > (UINT64_MAX - bits) / 8 ||
        length > (UINT64_MAX - bits) / 8 - buffered) __builtin_trap();
    const unsigned char *input = data;
    while (length) {
        size_t take = 128 - buffered;
        if (take > length) take = length;
        memcpy(ccdigest_data(di, ctx) + buffered, input, take);
        buffered += take;
        input += take;
        length -= take;
        if (buffered == 128) {
            di->compress(rpi5_digest_state(ctx), 1, ccdigest_data(di, ctx));
            bits += 1024;
            buffered = 0;
        }
    }
    rpi5_digest_set_num(di, ctx, (unsigned int)buffered);
    rpi5_digest_set_bits(ctx, bits);
}

/* Shared SHA-512/SHA-384 dispatch. Other descriptors are deliberately rejected;
 * these operations are not a generic/full crypto table. */
void
rpi5_sha512_digest_final(const struct ccdigest_info *di, ccdigest_ctx_t ctx,
    void *output)
{
    if (!supported(di) || ctx == NULL || output == NULL) __builtin_trap();
    final_digest(di, ctx, output);
}

void
rpi5_sha512_digest(const struct ccdigest_info *di, unsigned long length,
    const void *data, void *output)
{
    if (!supported(di) || output == NULL || (length && data == NULL))
        __builtin_trap();
    ccdigest_ctx_decl(64, 128, ctx);
    rpi5_sha512_digest_init(di, ctx);
    rpi5_sha512_digest_update(di, ctx, length, data);
    rpi5_sha512_digest_final(di, ctx, output);
    /* Do not retain the message tail in this one-shot temporary context. */
    volatile unsigned char *p=(volatile unsigned char *)ctx;
    for (size_t i=0;i<ccdigest_ctx_size(64,128);i++) p[i]=0;
}
