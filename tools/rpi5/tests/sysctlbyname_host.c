/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>

int rpi5_apple_sysctlbyname(const char *, void *, size_t *, void *, size_t);
static _Thread_local int injected_stage, injected_errno, calls;

/* Test-only boundary: normal mode invokes the real host kernel. Injection
 * verifies propagation at each of the original leaf's two syscall stages. */
int rpi5_test_sysctl(int *name, unsigned count, void *old, size_t *size,
                    void *value, size_t length)
{
    calls++;
    if (injected_stage == calls) { errno = injected_errno; return -1; }
    return sysctl(name, count, old, size, value, length);
}

static void *worker(void *unused)
{
    (void)unused;
    for (int i = 0; i < 1000; i++) {
        char original[128] = {0}, host[128] = {0};
        size_t a = sizeof(original), b = sizeof(host);
        calls = 0;
        assert(rpi5_apple_sysctlbyname("kern.ostype", original, &a, NULL, 0) == 0);
        assert(calls == 2 && sysctlbyname("kern.ostype", host, &b, NULL, 0) == 0);
        assert(a == b && memcmp(original, host, a) == 0);
        errno = 0; calls = 0; a = sizeof(original);
        assert(rpi5_apple_sysctlbyname("rpi5xnu.no.such.selector", original, &a, NULL, 0) == -1);
        assert(errno == ENOENT && calls == 1);
    }
    return NULL;
}

int main(void)
{
    pthread_t threads[8];
    for (int i = 0; i < 8; i++) assert(!pthread_create(&threads[i], NULL, worker, NULL));
    for (int i = 0; i < 8; i++) assert(!pthread_join(threads[i], NULL));
    for (int stage = 1; stage <= 2; stage++) {
        const int failures[] = {EACCES, ENOMEM, EFAULT, ENOENT, EPERM, ENOTSUP};
        for (unsigned i = 0; i < sizeof(failures) / sizeof(failures[0]); i++) {
            char bytes[128] = {0}; size_t size = sizeof(bytes);
            injected_stage = stage; injected_errno = failures[i]; calls = 0; errno = 0;
            assert(rpi5_apple_sysctlbyname("kern.ostype", bytes, &size, NULL, 0) == -1);
            assert(errno == failures[i] && calls == stage);
        }
    }
    injected_stage = 0;
    char small[1] = {0}; size_t size = sizeof(small);
    calls = 0; errno = 0;
    assert(rpi5_apple_sysctlbyname("kern.ostype", small, &size, NULL, 0) == -1);
    assert(errno == ENOMEM && calls == 2);
    size_t host_size = 0; size = 0;
    assert(rpi5_apple_sysctlbyname("kern.ostype", NULL, &size, NULL, 0) == 0);
    assert(sysctlbyname("kern.ostype", NULL, &host_size, NULL, 0) == 0 && size == host_size);
    const char *features[] = {"hw.optional.arm.FEAT_AES", "hw.optional.arm.FEAT_PMULL",
        "hw.optional.arm.FEAT_SHA1", "hw.optional.arm.FEAT_SHA256",
        "hw.optional.arm.FEAT_SHA512", "hw.optional.arm.FEAT_SHA3"};
    for (unsigned i = 0; i < 6; i++) {
        int original = -1, host = -1; size = sizeof(original); host_size = sizeof(host);
        errno = 0;
        int a = rpi5_apple_sysctlbyname(features[i], &original, &size, NULL, 0), e = errno;
        errno = 0;
        int b = sysctlbyname(features[i], &host, &host_size, NULL, 0), f = errno;
        assert(a == b && size == host_size);
        if (a) assert(e == f); else assert(original == host);
    }
    puts("RPI5XNU:SYSCTLBYNAME:PASS QUERIES=16000 INJECTED=12 FEATURES=6 SHORT_BUFFER=1 SIZE_ONLY=1 HOST_ONLY");
    return 0;
}
