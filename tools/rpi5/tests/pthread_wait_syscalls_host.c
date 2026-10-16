/* SPDX-License-Identifier: BSD-2-Clause
 * Real host kernel calls through namespaced copies of the actual trap code.
 * Does not call psynch without a genuine pthread sequence/registration state.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/ulock.h>

extern int rpi5_host_ulock_wait(uint32_t, void *, uint64_t, uint32_t);
extern int rpi5_host_ulock_wait2(uint32_t, void *, uint64_t, uint64_t, uint64_t);
extern int rpi5_host_ulock_wake(uint32_t, void *, uint64_t);

/* Host harness error bridge only. Target still imports cerror_nocancel. */
long rpi5_host_cerror(int error) { errno = error; return -1; }
static atomic_int ready;
static uint32_t lockword;

static void *errors(void *unused)
{
    (void)unused;
    uint32_t value = 0;
    for (unsigned i = 0; i < 2000; i++) {
        errno = EDOM;
        assert(rpi5_host_ulock_wait(0, &value, 0, 1000) == -1 && errno == EINVAL);
        errno = EDOM;
        assert(rpi5_host_ulock_wait(ULF_NO_ERRNO, &value, 0, 1000) == -EINVAL && errno == EDOM);
        errno = EDOM;
        assert(rpi5_host_ulock_wait2(0, &value, 0, 1000000, 0) == -1 && errno == EINVAL);
        errno = EDOM;
        assert(rpi5_host_ulock_wait2(ULF_NO_ERRNO, &value, 0, 1000000, 0) == -EINVAL && errno == EDOM);
        errno = EDOM;
        assert(rpi5_host_ulock_wake(0, &value, 0) == -1 && errno == EINVAL);
        errno = EDOM;
        assert(rpi5_host_ulock_wake(ULF_NO_ERRNO, &value, 0) == -EINVAL && errno == EDOM);
    }
    return NULL;
}

static void *waiter(void *unused)
{
    (void)unused;
    atomic_store(&ready, 1);
    assert(rpi5_host_ulock_wait2(UL_COMPARE_AND_WAIT | ULF_NO_ERRNO,
        &lockword, 0, 1000000000, 0) >= 0);
    return NULL;
}

int main(void)
{
    pthread_t threads[8], waiting;
    for (unsigned i = 0; i < 8; i++) assert(!pthread_create(&threads[i], NULL, errors, NULL));
    for (unsigned i = 0; i < 8; i++) assert(!pthread_join(threads[i], NULL));
    errno = EDOM;
    assert(rpi5_host_ulock_wait(UL_COMPARE_AND_WAIT, &lockword, 0, 1000) == -1 && errno == ETIMEDOUT);
    errno = EDOM;
    assert(rpi5_host_ulock_wait2(UL_COMPARE_AND_WAIT | ULF_NO_ERRNO,
        &lockword, 0, 1000000, 0) == -ETIMEDOUT && errno == EDOM);
    assert(!pthread_create(&waiting, NULL, waiter, NULL));
    while (!atomic_load(&ready)) sched_yield();
    int wake = -ENOENT;
    for (unsigned i = 0; i < 1000 && wake == -ENOENT; i++) {
        wake = rpi5_host_ulock_wake(UL_COMPARE_AND_WAIT | ULF_NO_ERRNO, &lockword, 0);
        if (wake == -ENOENT) usleep(100);
    }
    assert(wake == 0);
    assert(!pthread_join(waiting, NULL));
    puts("APPLE_WAIT_TRAPS PASS THREADS=8 REAL_ERRORS=96000 TIMEOUTS=2 WAKE=1 PSYNCH_NOT_EXECUTED HOST_ONLY");
    return 0;
}
