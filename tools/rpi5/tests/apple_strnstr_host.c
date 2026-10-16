/* SPDX-License-Identifier: BSD-2-Clause */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static char *oracle(const char *haystack, const char *needle, size_t limit)
{
    if (!needle[0]) return (char *)haystack;
    for (size_t at = 0; at < limit && haystack[at]; at++) {
        size_t j = 0;
        while (needle[j] && at + j < limit && haystack[at + j] &&
               needle[j] == haystack[at + j]) j++;
        if (!needle[j]) return (char *)haystack + at;
    }
    return NULL;
}

static unsigned word(char *out, unsigned index, unsigned maximum)
{
    for (unsigned length = 0, count = 1; length <= maximum; length++, count *= 3) {
        if (index < count) {
            for (unsigned i = 0; i < length; i++, index /= 3) out[i] = "abC"[index % 3];
            out[length] = 0;
            return length;
        }
        index -= count;
    }
    abort();
}

int main(void)
{
    unsigned cases = 0, boundaries = 0;
    for (unsigned alignment = 0; alignment < 4; alignment++)
        for (unsigned h = 0; h < 364; h++)
            for (unsigned n = 0; n < 40; n++) {
                char storage[16], needle[4];
                char *haystack = storage + alignment;
                word(haystack, h, 5); word(needle, n, 3);
                for (size_t limit = 0; limit < 8; limit++, cases++)
                    if (fixture_strnstr(haystack, needle, limit) != oracle(haystack, needle, limit)) return 1;
            }
    long page = sysconf(_SC_PAGESIZE);
    if (page < 129) return 2;
    char *mapping = mmap(NULL, (size_t)page * 2, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON, -1, 0);
    if (mapping == MAP_FAILED || mprotect(mapping + page, (size_t)page, PROT_NONE)) return 3;
    for (size_t length = 0; length <= 128; length++) {
        char *heap = malloc(length ? length : 1);
        if (!heap) return 4;
        char *edge = mapping + page - length;
        memset(heap, 'a', length); memset(edge, 'a', length);
        if (fixture_strnstr(heap, "b", length) || fixture_strnstr(edge, "b", length)) return 5;
        if (fixture_strnstr(heap, "", length) != heap || fixture_strnstr(edge, "", length) != edge) return 6;
        if (length) {
            edge[length - 1] = 'b'; heap[length - 1] = 'b';
            if (fixture_strnstr(edge, "b", length) != edge + length - 1 ||
                fixture_strnstr(heap, "b", length) != heap + length - 1) return 7;
            if (fixture_strnstr(edge, "ba", length) || fixture_strnstr(heap, "ba", length)) return 8;
            edge[length - 1] = 0; heap[length - 1] = 0;
            if (fixture_strnstr(edge, "b", length + 1) || fixture_strnstr(heap, "b", length + 1)) return 9;
        }
        free(heap); boundaries++;
    }
    if (munmap(mapping, (size_t)page * 2)) return 10;
    if (cases != 465920 || boundaries != 129) return 11;
    puts("APPLE_STRNSTR PASS CASES=465920 ALIGNMENTS=4 LIMITS=8 HEAP_GUARD_BOUNDARIES=129");
    return 0;
}
