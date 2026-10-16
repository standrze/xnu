/* SPDX-License-Identifier: BSD-2-Clause
 * Real process/thread lifecycle workload. Native runs exercise the workload
 * against host pthread, not the privately linked target providers/startup.
 */
#include <pthread.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>

#ifndef RPI5_PTHREAD_HOST
extern unsigned rpi5_pthread_startup_stage;
#endif
static unsigned constructor_ok, counter, destroyed, once_count, go;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static pthread_key_t key;
static pthread_t main_thread;
static uintptr_t errors[4], identities[4];

__attribute__((constructor)) static void initialized_constructor(void)
{
#ifndef RPI5_PTHREAD_HOST
    if (rpi5_pthread_startup_stage != 2) return;
#endif
    main_thread = pthread_self();
    if (!main_thread || !pthread_main_np() || pthread_mutex_lock(&lock)) return;
    void *p = calloc(8, 4);
    constructor_ok = p != 0;
    free(p);
    if (pthread_mutex_unlock(&lock)) constructor_ok = 0;
}

static void initialize_once(void) { once_count++; }
static void destroy_value(void *value)
{
    if (!value || pthread_mutex_lock(&lock)) _exit(131);
    destroyed++;
    if (pthread_mutex_unlock(&lock)) _exit(132);
}

static void *worker(void *argument)
{
    uintptr_t index = (uintptr_t)argument;
    if (!index || index > 4 || pthread_equal(pthread_self(), main_thread) ||
        pthread_main_np() || pthread_setspecific(key, argument)) return 0;
    errors[index-1] = (uintptr_t)&errno;
    identities[index-1] = (uintptr_t)pthread_self();
    while (!__atomic_load_n(&go, __ATOMIC_ACQUIRE)) {}
    for (unsigned i = 0; i < 512; i++) {
        if (pthread_once(&once, initialize_once) ||
            pthread_getspecific(key) != argument) return 0;
        unsigned char *p = malloc(31);
        if (!p) return 0;
        for (unsigned j = 0; j < 31; j++) p[j] = (unsigned char)(index+j);
        unsigned char *q = realloc(p, 73);
        if (!q) { free(p); return 0; }
        for (unsigned j = 0; j < 31; j++) {
            if (q[j] != (unsigned char)(index+j)) { free(q); return 0; }
        }
        free(q);
        errno = (int)(100 + index);
        if (pthread_mutex_lock(&lock)) return 0;
        counter++;
        if (pthread_mutex_unlock(&lock) || errno != (int)(100+index)) return 0;
    }
    return argument;
}

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    (void)argc; (void)argv;
    pthread_t workers[4];
    unsigned created = 0, failed = 0;
#ifndef RPI5_PTHREAD_HOST
    if (rpi5_pthread_startup_stage != 3) return 133;
#endif
    if (!constructor_ok || !pthread_equal(pthread_self(), main_thread) ||
        pthread_key_create(&key, destroy_value)) return 134;
    for (unsigned i = 0; i < 4; i++) {
        if (pthread_create(&workers[i], 0, worker, (void *)(uintptr_t)(i+1))) {
            failed = 1; break;
        }
        created++;
    }
    __atomic_store_n(&go, 1, __ATOMIC_RELEASE);
    for (unsigned i = 0; i < created; i++) {
        void *result = 0;
        if (pthread_join(workers[i], &result) || result != (void *)(uintptr_t)(i+1)) failed = 1;
    }
    for (unsigned i = 0; i < 4; i++) {
        if (!errors[i] || errors[i] == (uintptr_t)&errno || !identities[i]) failed = 1;
        for (unsigned j = 0; j < i; j++) {
            if (errors[i] == errors[j] || identities[i] == identities[j]) failed = 1;
        }
    }
    if (pthread_key_delete(key) || failed || created != 4 || counter != 2048 ||
        destroyed != 4 || once_count != 1) return 135;
    static const char result[] = "PTHREAD:SMOKE PASS CTOR=1 THREADS=4 JOIN=4 MUTEX=2048 TSD_DTORS=4 ONCE=1 ERRNO=4 ALLOC=2048\n";
    if (write(1, result, sizeof(result)-1) != sizeof(result)-1) return 136;
    return 0;
}

#ifdef RPI5_PTHREAD_HOST
int main(int argc, char **argv) { return rpi5_pthread_smoke_main(argc, argv); }
#endif
