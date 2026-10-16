/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

extern void *rpi5_native__platform_memset(void *, int, size_t);
extern void rpi5_native__platform_bzero(void *, size_t);
extern size_t rpi5_native__platform_strlen(const char *);
extern void *rpi5_native__platform_memmove(void *, const void *, size_t);
extern void rpi5_native__platform_memset_pattern4(void *, const void *, size_t);
extern void rpi5_native__platform_memset_pattern8(void *, const void *, size_t);
extern void rpi5_native__platform_memset_pattern16(void *, const void *, size_t);
extern void rpi5_host_exit(int) __attribute__((noreturn));
long rpi5_host_cerror(int error) { errno = error; return -1; }

int main(void)
{
    unsigned char actual[1024], expected[1024], pattern[16];
    unsigned cases = 0;
    for (unsigned i = 0; i < sizeof(pattern); i++) pattern[i] = (unsigned char)(i * 13 + 3);
    for (size_t offset = 0; offset < 32; offset++) {
        for (size_t len = 0; len <= 513; len++) {
            memset(actual, 0xa5, sizeof(actual));
            memcpy(expected, actual, sizeof(actual));
            memset(expected + offset, 0x180 + (int)offset, len);
            assert(rpi5_native__platform_memset(actual + offset, 0x180 + (int)offset, len) == actual + offset);
            assert(!memcmp(actual, expected, sizeof(actual))); cases++;
            memset(expected + offset, 0, len);
            rpi5_native__platform_bzero(actual + offset, len);
            assert(!memcmp(actual, expected, sizeof(actual))); cases++;
            for (unsigned width = 4; width <= 16; width *= 2) {
                memset(actual, 0xa5, sizeof(actual));
                memcpy(expected, actual, sizeof(actual));
                for (size_t j = 0; j < len; j++) expected[offset + j] = pattern[j % width];
                if (width == 4) rpi5_native__platform_memset_pattern4(actual + offset, pattern, len);
                if (width == 8) rpi5_native__platform_memset_pattern8(actual + offset, pattern, len);
                if (width == 16) rpi5_native__platform_memset_pattern16(actual + offset, pattern, len);
                assert(!memcmp(actual, expected, sizeof(actual))); cases++;
            }
            for (int direction = -1; direction <= 1; direction++) {
                for (size_t j = 0; j < sizeof(actual); j++) actual[j] = (unsigned char)(j * 31);
                memcpy(expected, actual, sizeof(actual));
                size_t src = 64 + offset, dst = (size_t)((int)src + direction * 17);
                memmove(expected + dst, expected + src, len);
                assert(rpi5_native__platform_memmove(actual + dst, actual + src, len) == actual + dst);
                assert(!memcmp(actual, expected, sizeof(actual))); cases++;
            }
        }
    }
    size_t page = (size_t)getpagesize();
    unsigned char *mapping = mmap(NULL, 3 * page, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(mapping != MAP_FAILED);
    unsigned char *middle = mapping + page;
    assert(!mprotect(middle, page, PROT_READ | PROT_WRITE));
    unsigned lengths = 0;
    /* The original word scanner may load bytes after NUL within its aligned
     * word. Exercise page edges without falsely requiring byte-at-a-time reads. */
    for (size_t len = 0; len < 1024; len++) {
        memset(middle, 0x81, page);
        middle[page - 1] = 0;
        assert(rpi5_native__platform_strlen((char *)middle + page - 1 - len) == len); lengths++;
        memset(middle, 'x', page);
        middle[len] = 0;
        assert(rpi5_native__platform_strlen((char *)middle) == len); lengths++;
    }
    assert(!munmap(mapping, 3 * page));
    pid_t child = fork(); assert(child >= 0);
    if (child == 0) rpi5_host_exit(37);
    int status = 0;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 37);
    printf("APPLE_MEMORY_PROVIDERS PASS CASES=%u GUARDED_STRLEN=%u REAL_EXIT=37 REGISTRATION_NOT_EXECUTED WORKQ_NOT_EXECUTED HOST_ONLY\n", cases, lengths);
    return 0;
}
