/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit syscall doubles. Public synthetic bytes, never host entropy.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>
#include <openssl/rand.h>

void fixture_arc4random_buf(void *, size_t);
static _Atomic unsigned total_calls, workers_ready;
static _Atomic int finish;
static _Thread_local unsigned calls, fail_on;
static _Thread_local int error_code;

int fixture_getentropy(void *buffer, size_t size)
{
    assert(buffer != NULL && size > 0 && size <= 256);
    calls++;
    atomic_fetch_add_explicit(&total_calls, 1, memory_order_relaxed);
    if (buffer == (void *)(uintptr_t)1) { errno = EFAULT; return -1; }
    if (calls == fail_on) { errno = error_code; return -1; }
    unsigned char *p = buffer;
    for (size_t i = 0; i < size; i++) p[i] = 0xa5;
    return 0;
}

static void boundary(size_t size)
{
    unsigned char buffer[4098];
    assert(size <= 4097);
    for (size_t i = 0; i < sizeof(buffer); i++) buffer[i] = 0x5a;
    calls = 0; errno = EALREADY;
    fixture_arc4random_buf(buffer, size);
    assert(calls == (size + 255) / 256 && errno == EALREADY);
    for (size_t i = 0; i < size; i++) assert(buffer[i] == 0xa5);
    for (size_t i = size; i < sizeof(buffer); i++) assert(buffer[i] == 0x5a);
}

static void *worker(void *unused)
{
    (void)unused;
    atomic_fetch_add_explicit(&workers_ready, 1, memory_order_release);
    unsigned count = 0;
    do { boundary(1025); count++; }
    while (!atomic_load_explicit(&finish, memory_order_acquire) || count < 100);
    return NULL;
}

static void expect_fatal(unsigned mode)
{
    pid_t child = fork(); assert(child >= 0);
    if (child == 0) {
        unsigned char bytes[513]; calls = 0;
        fail_on = mode >= 2 ? mode - 1 : 0;
        error_code = mode == 3 ? EINTR : EIO;
        if (mode == 0) fixture_arc4random_buf(NULL, 1);
        else if (mode == 1) fixture_arc4random_buf((void *)(UINTPTR_MAX - 7), 9);
        else if (mode == 6) fixture_arc4random_buf((void *)(uintptr_t)1, 1);
        else if (mode == 7) fixture_arc4random_buf(bytes, SIZE_MAX);
        else if (mode == 5) {
            fail_on = 2;
            (void)RAND_bytes(bytes, sizeof(bytes));
        } else fixture_arc4random_buf(bytes, sizeof(bytes));
        _exit(99); /* Any return from a failed request is a test failure. */
    }
    int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 127);
}

int main(void)
{
    calls = 0; fixture_arc4random_buf(NULL, 0); assert(calls == 0);
    const size_t lengths[] = {0,1,255,256,257,511,512,513,1024,1025,4097};
    for (unsigned i = 0; i < sizeof(lengths)/sizeof(lengths[0]); i++) boundary(lengths[i]);
    unsigned char buffer[513]; calls = 0;
    assert(RAND_bytes(buffer, sizeof(buffer)) == 1 && calls == 3);
    for (unsigned i = 0; i < sizeof(buffer); i++) assert(buffer[i] == 0xa5);
    assert(RAND_bytes(NULL, 0) == 1 && calls == 3);
    /* Preserve the ORIGINAL LibreSSL num<=0 behavior; adapter isn't called. */
    assert(RAND_bytes(NULL, -1) == 1 && calls == 3);
    for (unsigned mode = 0; mode < 8; mode++) expect_fatal(mode);
    pthread_t threads[4];
    for (unsigned i = 0; i < 4; i++) assert(!pthread_create(&threads[i], NULL, worker, NULL));
    while (atomic_load_explicit(&workers_ready, memory_order_acquire) != 4) { }
    pid_t child = fork(); assert(child >= 0);
    if (child == 0) {
        calls = 0; fail_on = 0;
        fixture_arc4random_buf(buffer, sizeof(buffer));
        for (unsigned i = 0; i < sizeof(buffer); i++) if (buffer[i] != 0xa5) _exit(98);
        _exit(calls == 3 ? 0 : 97);
    }
    int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    atomic_store_explicit(&finish, 1, memory_order_release);
    for (unsigned i = 0; i < 4; i++) assert(!pthread_join(threads[i], NULL));
    puts("KERNEL_ENTROPY_ADAPTER_CONTRACT_PASS BOUNDARIES=11 FATAL=8 THREADS=4 FORK_WHILE_ACTIVE=1 ORIGINAL_RAND_BYTES=1 SYSCALL_DOUBLES_NOT_ENTROPY");
    return 0;
}
