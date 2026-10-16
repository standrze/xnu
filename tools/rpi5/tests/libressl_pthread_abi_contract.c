/* SPDX-License-Identifier: BSD-2-Clause
 * Compiled twice for arm64: SDK declarations consumed by LibreSSL/workload,
 * and the selected original Apple pthread public headers. Objects never run.
 */
#include <pthread/pthread.h>
#include <stddef.h>
#include <stdint.h>

const struct {
    uint64_t fields[12];
    pthread_mutex_t mutex;
    pthread_once_t once;
} rpi5_pthread_abi = {
    { sizeof(pthread_t), sizeof(pthread_key_t), sizeof(pthread_mutex_t),
      _Alignof(pthread_mutex_t), offsetof(pthread_mutex_t, __sig),
      offsetof(pthread_mutex_t, __opaque), sizeof(pthread_once_t),
      _Alignof(pthread_once_t), sizeof(pthread_cond_t),
      _Alignof(pthread_cond_t), sizeof(pthread_attr_t), _Alignof(pthread_attr_t) },
    PTHREAD_MUTEX_INITIALIZER, PTHREAD_ONCE_INIT
};

__attribute__((used)) static int (*lock_fn)(pthread_mutex_t *) = pthread_mutex_lock;
__attribute__((used)) static int (*unlock_fn)(pthread_mutex_t *) = pthread_mutex_unlock;
__attribute__((used)) static int (*equal_fn)(pthread_t, pthread_t) = pthread_equal;
__attribute__((used)) static pthread_t (*self_fn)(void) = pthread_self;
__attribute__((used)) static int (*once_fn)(pthread_once_t *, void (*)(void)) = pthread_once;
