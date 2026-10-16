/* SPDX-License-Identifier: BSD-2-Clause
 * Exercise namespaced, otherwise original Apple platform implementations.
 * Host pthread/Mach services are real macOS services, not target qualification.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <libkern/OSAtomic.h>
#include <os/lock.h>
#include <os/once_private.h>
#include <os/semaphore_private.h>
#include <os/os_sync_wait_on_address.h>

enum { THREADS = 8, ITERATIONS = 20000 };
static os_unfair_lock lock = OS_UNFAIR_LOCK_INIT;
static os_once_t once;
static unsigned counter, once_calls, published;
static volatile int32_t atomic_counter;
static atomic_int ready, start, hold_ready, hold_release;
static os_semaphore_t semaphore;

static void initialize(void *context)
{
    assert(context == &published);
    /* Give other threads an opportunity to enter the real wait path. */
    usleep(20000);
    once_calls++;
    published = 0x51a7;
}

static void *worker(void *unused)
{
    (void)unused;
    atomic_fetch_add(&ready, 1);
    while (!atomic_load(&start)) sched_yield();
    _os_once(&once, &published, initialize);
    assert(published == 0x51a7);
    for (unsigned i = 0; i < ITERATIONS; i++) {
        os_unfair_lock_lock(&lock);
        os_unfair_lock_assert_owner(&lock);
        counter++;
        os_unfair_lock_unlock(&lock);
        OSAtomicIncrement32Barrier(&atomic_counter);
    }
    _os_semaphore_signal(semaphore);
    return NULL;
}

static void *holder(void *unused)
{
    (void)unused;
    os_unfair_lock_lock(&lock);
    atomic_store(&hold_ready, 1);
    while (!atomic_load(&hold_release)) sched_yield();
    os_unfair_lock_unlock(&lock);
    return NULL;
}

int main(void)
{
    pthread_t threads[THREADS], held;
    semaphore = _os_semaphore_create();
    for (unsigned i = 0; i < THREADS; i++) assert(!pthread_create(&threads[i], NULL, worker, NULL));
    while (atomic_load(&ready) != THREADS) sched_yield();
    atomic_store(&start, 1);
    for (unsigned i = 0; i < THREADS; i++) _os_semaphore_wait(semaphore);
    for (unsigned i = 0; i < THREADS; i++) assert(!pthread_join(threads[i], NULL));
    _os_semaphore_dispose(semaphore);
    assert(counter == THREADS * ITERATIONS);
    assert(atomic_counter == THREADS * ITERATIONS);
    assert(once_calls == 1);
    for (unsigned i = 0; i < 1000; i++) _os_once(&once, &published, initialize);
    assert(once_calls == 1);
    assert(!pthread_create(&held, NULL, holder, NULL));
    while (!atomic_load(&hold_ready)) sched_yield();
    assert(!os_unfair_lock_trylock(&lock));
    os_unfair_lock_assert_not_owner(&lock);
    atomic_store(&hold_release, 1);
    assert(!pthread_join(held, NULL));
    assert(os_unfair_lock_trylock(&lock));
    os_unfair_lock_unlock(&lock);
    uint64_t address = 0;
    errno = 0;
    assert(os_sync_wait_on_address(&address, 0, 3, 0) == -1 && errno == EINVAL);
    errno = 0;
    assert(os_sync_wake_by_address_all(&address, 3, 0) == -1 && errno == EINVAL);
    puts("APPLE_PLATFORM PASS THREADS=8 LOCKED=160000 ATOMIC=160000 ONCE=1 SEMAPHORE=8 FAILURE_CASES=3 HOST_ONLY");
    return 0;
}
