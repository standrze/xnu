/* SPDX-License-Identifier: BSD-2-Clause
 * Target candidate for the genuine Apple PTHREAD_MUTEX_RECURSIVE path.
 * A host build is a behavior oracle only; it is never target evidence.
 */
#include <pthread.h>
#include <errno.h>
#include <stdint.h>
#include <unistd.h>

#ifndef RPI5_PTHREAD_RECURSIVE_HOST
extern unsigned rpi5_pthread_startup_stage;
#endif

static pthread_mutex_t recursive_mutex;
static int foreign_unlock[2];
static int foreign_trylock[2];
static unsigned worker_index;

static void *probe_owned_mutex(void *argument)
{
    unsigned index = (unsigned)(uintptr_t)argument;
    if (index > 1) return (void *)(uintptr_t)0x7f;
    foreign_unlock[index] = pthread_mutex_unlock(&recursive_mutex);
    foreign_trylock[index] = pthread_mutex_trylock(&recursive_mutex);
    if (foreign_trylock[index] == 0) {
        (void)pthread_mutex_unlock(&recursive_mutex);
    }
    worker_index |= 1u << index;
    return argument;
}

static void *probe_released_mutex(void *argument)
{
    int result = pthread_mutex_lock(&recursive_mutex);
    if (result) return (void *)(uintptr_t)(0x100u + (unsigned)result);
    result = pthread_mutex_unlock(&recursive_mutex);
    return result ? (void *)(uintptr_t)(0x200u + (unsigned)result) : argument;
}

static int run_worker(void *(*entry)(void *), uintptr_t token)
{
    pthread_t thread;
    void *result = 0;
    int error = pthread_create(&thread, 0, entry, (void *)token);
    if (error) return error;
    error = pthread_join(thread, &result);
    if (error) return error;
    return result == (void *)token ? 0 : EINVAL;
}

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    pthread_mutexattr_t attributes;
    int type = 0;
    (void)argc;
    (void)argv;
#ifndef RPI5_PTHREAD_RECURSIVE_HOST
    if (rpi5_pthread_startup_stage != 3) return 141;
#endif
    if (pthread_mutexattr_init(&attributes)) return 142;
    if (pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE)) return 143;
    if (pthread_mutexattr_gettype(&attributes, &type) ||
        type != PTHREAD_MUTEX_RECURSIVE) return 144;
    if (pthread_mutex_init(&recursive_mutex, &attributes)) return 145;
    if (pthread_mutexattr_destroy(&attributes)) return 146;

    if (pthread_mutex_lock(&recursive_mutex)) return 147;
    if (pthread_mutex_lock(&recursive_mutex)) return 148;
    if (pthread_mutex_trylock(&recursive_mutex)) return 149;
    if (run_worker(probe_owned_mutex, 0)) return 150;
    if (pthread_mutex_unlock(&recursive_mutex)) return 151;
    if (run_worker(probe_owned_mutex, 1)) return 152;
    if (pthread_mutex_unlock(&recursive_mutex)) return 153;
    if (pthread_mutex_unlock(&recursive_mutex)) return 154;
    if (run_worker(probe_released_mutex, 2)) return 155;

    if (worker_index != 3u || foreign_unlock[0] != EPERM ||
        foreign_unlock[1] != EPERM || foreign_trylock[0] != EBUSY ||
        foreign_trylock[1] != EBUSY) return 156;
    if (pthread_mutex_destroy(&recursive_mutex)) return 157;

    static const char result[] =
        "PTHREAD:RECURSIVE PASS DEPTH=3 FOREIGN_EPERM=2 BUSY=2 RELEASED=1\n";
    if (write(1, result, sizeof(result) - 1) != sizeof(result) - 1) return 158;
    return 0;
}

#ifdef RPI5_PTHREAD_RECURSIVE_HOST
int main(int argc, char **argv) { return rpi5_pthread_smoke_main(argc, argv); }
#endif
