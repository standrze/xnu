/* SPDX-License-Identifier: BSD-2-Clause */
/* Current original Apple Libc leaf semantics; not a timing measurement. */
#define __STDC_WANT_LIB_EXT1__ 1
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int timingsafe_bcmp(const void *, const void *, size_t);
int main(void)
{
    unsigned char a[515], b[515]; unsigned cases = 0;
    for (size_t n = 0; n <= 512; n++) {
        for (size_t i = 0; i < sizeof(a); i++) a[i] = b[i] = (unsigned char)(i * 37);
        assert(timingsafe_bcmp(a + 1, b + 1, n) == 0); cases++;
        for (size_t i = 0; i < n; i++) {
            b[1 + i] ^= 0x81;
            assert(timingsafe_bcmp(a + 1, b + 1, n) == 1); cases++;
            b[1 + i] ^= 0x81;
        }
        assert(!memcmp(a, b, sizeof(a)));
    }
    assert(!timingsafe_bcmp(NULL, NULL, 0)); cases++;
    memset(a, 0x42, sizeof(a));
    assert(memset_s(NULL, 0, 0, 0) == EINVAL);
    assert(memset_s(a, RSIZE_MAX + 1, 0, 1) == E2BIG && a[0] == 0x42);
    assert(memset_s(a, 13, 0, RSIZE_MAX + 1) == E2BIG);
    for (unsigned i = 0; i < 13; i++) assert(!a[i]);
    assert(a[13] == 0x42);
    memset(a, 0x42, sizeof(a));
    assert(memset_s(a, 13, 0, 14) == EOVERFLOW);
    for (unsigned i = 0; i < 13; i++) assert(!a[i]);
    assert(a[13] == 0x42);
    assert(!memset_s(a + 1, 12, 0x142, 12));
    for (unsigned i = 1; i < 13; i++) assert(a[i] == 0x42);
    assert(!a[0] && a[13] == 0x42);
    assert(!memset_s(a, 0, 0, 0) && !a[0]);
    printf("RPI5XNU:SSHLEAF:PASS COMPARES=%u MEMSET_CASES=6 NO_TIMING_OR_TRANSPORT_PROOF\n", cases);
    return 0;
}
