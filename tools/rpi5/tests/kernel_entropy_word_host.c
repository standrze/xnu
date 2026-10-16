/* SPDX-License-Identifier: BSD-2-Clause
 * Synthetic byte-source sequences test API delegation and rejection math.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint32_t fixture_arc4random(void);
uint32_t fixture_arc4random_uniform(uint32_t);
static const uint32_t *words;
static size_t count, consumed;

void fixture_arc4random_buf(void *buffer, size_t size)
{
    if (size != sizeof(uint32_t) || consumed >= count) abort();
    memcpy(buffer, &words[consumed++], size);
}

static int check(uint32_t bound, const uint32_t *sequence, size_t length,
    uint32_t expected, size_t draws)
{
    words = sequence;
    count = length;
    consumed = 0;
    return fixture_arc4random_uniform(bound) != expected || consumed != draws;
}

int main(void)
{
    static const uint32_t all[] = {UINT32_MAX};
    static const uint32_t thirds[] = {0, UINT32_MAX};
    static const uint32_t fifths[] = {0, 1};
    static const uint32_t sevenths[] = {0, 3, 4};
    static const uint32_t large[] = {0, 0x7ffffffe, 0x80000000};
    static const uint32_t maximum[] = {0, UINT32_MAX - 1};
    uint32_t word = 0x89abcdef;
    words = &word; count = 1; consumed = 0;
    if (fixture_arc4random() != word || consumed != 1) return 1;
    if (check(0, NULL, 0, 0, 0) || check(1, NULL, 0, 0, 0) ||
        check(2, all, 1, 1, 1) || check(3, thirds, 2, 0, 2) ||
        check(5, fifths, 2, 1, 2) || check(7, sevenths, 3, 4, 3) ||
        check(65536, all, 1, 65535, 1) ||
        check(0x80000000, all, 1, 0x7fffffff, 1) ||
        check(0x80000001, large, 3, 0x80000000, 3) ||
        check(UINT32_MAX, maximum, 2, UINT32_MAX - 1, 2)) return 2;
    /* Each accepted residue appears equally often over a complete multiple
     * of the bound, starting at the original sampler's exact threshold. */
    for (uint32_t bound = 2; bound <= 257; ++bound) {
        uint32_t minimum = (uint32_t)(-bound) % bound;
        unsigned hits[257] = {0};
        for (uint32_t n = 0; n < bound * 4; ++n) {
            word = minimum + n; words = &word; count = 1; consumed = 0;
            uint32_t value = fixture_arc4random_uniform(bound);
            if (value >= bound || consumed != 1) return 3;
            hits[value]++;
        }
        for (uint32_t n = 0; n < bound; ++n) if (hits[n] != 4) return 4;
    }
    puts("KERNEL_RANDOM_WORD_API PASS WORD=1 BOUNDS=10 RESIDUE_GROUPS=256 SYNTHETIC_SOURCE");
    return 0;
}
