/* SPDX-License-Identifier: BSD-2-Clause */
/* Public, fixed test vectors only. No generated/session keys or entropy claim.
 * RFC 8439 A.1 vector 1 has the same all-zero state for the original 64-bit
 * nonce ChaCha implementation; this does NOT test the IETF AEAD construction.
 * Poly1305 vector: RFC 8439 section 2.5.2.
 * https://www.rfc-editor.org/rfc/rfc8439
 */
#include "includes.h"
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include "chacha.h"
#include "poly1305.h"

static int emit(const char *s)
{
    size_t n = strlen(s);
    for (unsigned attempts = 0; n && attempts < 64; attempts++) {
        ssize_t done = write(1, s, n);
        if (done < 0 && errno == EINTR) continue;
        if (done <= 0 || (size_t)done > n) return -1;
        s += done;
        n -= (size_t)done;
    }
    return n ? -1 : 0;
}

static unsigned digit(char c)
{
    return c <= '9' ? (unsigned)(c - '0') : (unsigned)(c - 'a' + 10);
}

static void decode(unsigned char *out, const char *hex, size_t n)
{
    for (size_t i = 0; i < n; i++)
        out[i] = (unsigned char)((digit(hex[2 * i]) << 4) | digit(hex[2 * i + 1]));
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    if (emit("RPI5XNU:SSHCRYPTO:BEGIN ORIGINAL_CHACHA_POLY1305 PUBLIC_VECTORS NO_KEYS\n")) return 2;
    unsigned char key[32] = {0}, nonce[8] = {0}, counter[8] = {0};
    unsigned char input[256] = {0}, output[258], expected[64], recovered[258];
    struct chacha_ctx state;
    decode(expected,
        "76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7"
        "da41597c5157488d7724e03fb8d84a376a43b8f41518a11cc387b669b2ee6586", 64);
    chacha_keysetup(&state, key, 256);
    chacha_ivsetup(&state, nonce, counter);
    memset(output, 0xa5, sizeof(output));
    chacha_encrypt_bytes(&state, input, output + 1, 64);
    if (memcmp(output + 1, expected, 64) || output[0] != 0xa5 || output[65] != 0xa5) goto failed;

    const unsigned lengths[] = {0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 255, 256};
    for (unsigned i = 0; i < sizeof(input); i++) input[i] = (unsigned char)(i * 37U + 11U);
    for (unsigned i = 0; i < sizeof(key); i++) key[i] = (unsigned char)(i * 13U + 7U);
    for (unsigned i = 0; i < sizeof(nonce); i++) nonce[i] = (unsigned char)(i * 17U + 3U);
    counter[0] = 7;
    for (unsigned i = 0; i < sizeof(lengths) / sizeof(lengths[0]); i++) {
        unsigned n = lengths[i];
        memset(output, 0xa5, sizeof(output));
        memset(recovered, 0x5a, sizeof(recovered));
        chacha_keysetup(&state, key, 256);
        chacha_ivsetup(&state, nonce, counter);
        chacha_encrypt_bytes(&state, input, output + 1, n);
        chacha_keysetup(&state, key, 256);
        chacha_ivsetup(&state, nonce, counter);
        chacha_encrypt_bytes(&state, output + 1, recovered + 1, n);
        if (memcmp(input, recovered + 1, n) || output[0] != 0xa5 || output[n + 1] != 0xa5 ||
            recovered[0] != 0x5a || recovered[n + 1] != 0x5a) goto failed;
        chacha_keysetup(&state, key, 256);
        chacha_ivsetup(&state, nonce, counter);
        chacha_encrypt_bytes(&state, output + 1, output + 1, n);
        if (memcmp(input, output + 1, n) || output[0] != 0xa5 || output[n + 1] != 0xa5) goto failed;
    }

    decode(key, "85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b", 32);
    decode(expected, "a8061dc1305136c6c22b8baf0c0127a9", 16);
    const unsigned char message[] = "Cryptographic Forum Research Group";
    memset(output, 0xa5, sizeof(output));
    poly1305_auth(output + 1, message, sizeof(message) - 1, key);
    if (memcmp(output + 1, expected, 16) || output[0] != 0xa5 || output[17] != 0xa5) goto failed;
    poly1305_auth(output + 1, message, 0, key);
    if (memcmp(output + 1, key + 16, 16) || output[0] != 0xa5 || output[17] != 0xa5) goto failed;

    if (emit("RPI5XNU:SSHCRYPTO:PASS TWO_KATS BOUNDARIES IN_PLACE NOT_SSH_ENTROPY_OR_AEAD_PROOF\n")) return 2;
    return 0;
failed:
    (void)emit("RPI5XNU:SSHCRYPTO:FAIL NO_SECURITY_CLAIM\n");
    return 1;
}
