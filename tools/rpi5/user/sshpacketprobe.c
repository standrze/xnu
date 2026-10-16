/* SPDX-License-Identifier: BSD-2-Clause */
/* Fixed public test material; no session keys, entropy or live network. */
#include "includes.h"
#include <stdio.h>
#include <string.h>
#include "cipher-chachapoly.h"
#include "ssherr.h"

static int filled(const unsigned char *p, size_t n, unsigned char value)
{
    for (size_t i = 0; i < n; i++) if (p[i] != value) return 0;
    return 1;
}

int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    unsigned char key[64], plain[260], cipher[278], output[278], mutated[276];
    const unsigned lengths[] = {0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 255, 256};
    const unsigned sequences[] = {0, 1, 0x80000000u, 0xffffffffu};
    unsigned accepted = 0, rejected = 0;
    for (unsigned i = 0; i < sizeof key; i++) key[i] = (unsigned char)(i * 19 + 7);
    struct chachapoly_ctx *ctx = chachapoly_new(key, sizeof key);
    if (!ctx) return 2;
    struct chachapoly_ctx *bad = chachapoly_new(key, sizeof key - 1);
    if (bad) { chachapoly_free(bad); goto failed; }
    for (unsigned i = 0; i < sizeof lengths / sizeof lengths[0]; i++) {
        unsigned n = lengths[i], bytes = 4 + n + POLY1305_TAGLEN;
        memset(plain, 0, sizeof plain);
        plain[2] = (unsigned char)(n >> 8); plain[3] = (unsigned char)n;
        for (unsigned j = 4; j < 4 + n; j++) plain[j] = (unsigned char)(j * 37 + i);
        for (unsigned k = 0; k < sizeof sequences / sizeof sequences[0]; k++) {
            unsigned seq = sequences[k], decoded = 0xfefefefe;
            memset(cipher, 0xa5, sizeof cipher);
            if (chachapoly_crypt(ctx, seq, cipher + 1, plain, n, 4, POLY1305_TAGLEN, 1)) goto failed;
            if (cipher[0] != 0xa5 || !filled(cipher + 1 + bytes, sizeof cipher - 1 - bytes, 0xa5)) goto failed;
            for (unsigned short_len = 0; short_len < 4; short_len++) {
                if (chachapoly_get_length(ctx, &decoded, seq, cipher + 1, short_len) != SSH_ERR_MESSAGE_INCOMPLETE ||
                    decoded != 0xfefefefe) goto failed;
            }
            if (chachapoly_get_length(ctx, &decoded, seq, cipher + 1, 4) || decoded != n) goto failed;
            memset(output, 0x5a, sizeof output);
            if (chachapoly_crypt(ctx, seq, output + 1, cipher + 1, n, 4, POLY1305_TAGLEN, 0) ||
                memcmp(output + 1, plain, n + 4) || output[0] != 0x5a ||
                !filled(output + 5 + n, sizeof output - 5 - n, 0x5a)) goto failed;
            memcpy(output + 1, cipher + 1, bytes);
            if (chachapoly_crypt(ctx, seq, output + 1, output + 1, n, 4, POLY1305_TAGLEN, 0) ||
                memcmp(output + 1, plain, n + 4)) goto failed;
            accepted++;
            /* Every encrypted header, payload and tag byte is authenticated.
             * A failed MAC must leave the entire destination untouched. */
            for (unsigned j = 0; j < bytes; j++) {
                memcpy(mutated, cipher + 1, bytes); mutated[j] ^= 1;
                memset(output, 0x5a, sizeof output);
                if (chachapoly_crypt(ctx, seq, output + 1, mutated, n, 4, POLY1305_TAGLEN, 0) != SSH_ERR_MAC_INVALID ||
                    !filled(output, sizeof output, 0x5a)) goto failed;
                rejected++;
            }
            memset(output, 0x5a, sizeof output);
            if (chachapoly_crypt(ctx, seq ^ 2, output + 1, cipher + 1, n, 4, POLY1305_TAGLEN, 0) != SSH_ERR_MAC_INVALID ||
                !filled(output, sizeof output, 0x5a)) goto failed;
            rejected++;
        }
    }
    chachapoly_free(ctx);
    printf("RPI5XNU:SSHPACKET:PASS CASES=%u REJECTED=%u NO_TRANSPORT_OR_ENTROPY_PROOF\n", accepted, rejected);
    return 0;
failed:
    chachapoly_free(ctx);
    puts("RPI5XNU:SSHPACKET:FAIL");
    return 1;
}
