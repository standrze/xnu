/* SPDX-License-Identifier: BSD-2-Clause */
#include <stdio.h>
#include <string.h>

int main(void)
{
    unsigned cases = 0;
    for (unsigned from = 0; from < 16; from++)
        for (unsigned to = 0; to < 16; to++)
            for (unsigned length = 0; length < 256; length++) {
                unsigned char source[288], target[288];
                memset(source, 0x5a, sizeof(source));
                memset(target, 0xa5, sizeof(target));
                for (unsigned i = 0; i < length; i++) source[from + i] = (unsigned char)(1 + i % 255);
                source[from + length] = 0;
                char *end = fixture_stpcpy((char *)target + to, (char *)source + from);
                if (end != (char *)target + to + length ||
                    memcmp(target + to, source + from, length + 1)) return 1;
                for (unsigned i = 0; i < to; i++) if (target[i] != 0xa5) return 2;
                for (unsigned i = to + length + 1; i < sizeof(target); i++)
                    if (target[i] != 0xa5) return 3;
                cases++;
            }
    if (cases != 65536) return 4;
    puts("APPLE_STPCPY PASS CASES=65536 SOURCE_ALIGNMENTS=16 DEST_ALIGNMENTS=16 LENGTHS=256");
    return 0;
}
