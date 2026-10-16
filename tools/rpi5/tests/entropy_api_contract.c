/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit API doubles. No host entropy, Pi execution, or quality test.
 */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <sys/sysctl.h>
static unsigned calls, queries;
static int mode;
int fixture_getentropy(void *p, size_t n)
{
    unsigned call = calls++;
    assert(call < 5);
    if (call == 0) { assert(n == 0); return 0; }
    if (call <= 2) {
        assert(n == (call == 1 ? 1u : 256u));
        if (mode == 6) { errno = EIO; return -1; }
        memset(p, 0xa5, n); return 0;
    }
    if (call == 3) { assert(n == 257); errno = mode == 7 ? ENOSYS : EINVAL; return -1; }
    assert(p == (void *)(uintptr_t)1 && n == 1);
    if (mode == 8) return 0;
    errno = EFAULT; return -1;
}
int fixture_sysctlbyname(const char *name, void *out, size_t *size, void *in, size_t in_size)
{
    unsigned index = queries++;
    assert(calls == 5 && index < 10 && !in && !in_size);
    assert(!strncmp(name, "kern.entropy.", 13));
    assert(!strstr(name, "analysis") && !strstr(name, "buffer"));
    assert(*size == (index >= 7 ? 8u : 4u));
    if (mode == 2) { errno = ENOENT; return -1; }
    if (mode == 3) { --*size; return 0; }
    uint64_t value = index ? 0 : mode == 1 ? 0 : mode == 4 ? 2 : 1;
    if (mode == 5 && (index == 2 || index == 5)) value = 1;
    memcpy(out, &value, *size);
    return 0;
}
int rpi5_packet_pthread_prerequisite(int argc, char **argv)
{
    (void)argc; (void)argv; return mode == 9 ? 7 : 0;
}
int rpi5_pthread_smoke_main(int, char **);
int main(int argc, char **argv)
{
    assert(argc == 2); mode = atoi(argv[1]);
    int result = rpi5_pthread_smoke_main(argc, argv);
    unsigned expected_calls = mode == 9 ? 0 : mode == 6 ? 2 : mode == 7 ? 4 : 5;
    assert(calls == expected_calls);
    assert(queries == (mode >= 6 ? 0u : 10u));
    return result;
}
