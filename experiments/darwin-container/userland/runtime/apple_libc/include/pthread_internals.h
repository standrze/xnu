/* Project single-thread build lock ABI. No pthreads are created by this guest. */
#ifndef DARWIN_STATIC_ALLOCATOR_LOCK_H
#define DARWIN_STATIC_ALLOCATOR_LOCK_H
typedef volatile int pthread_lock_t;
static inline void apple_lock(pthread_lock_t *lock) {
    while (__atomic_exchange_n(lock, 1, __ATOMIC_ACQUIRE)) {}
}
static inline void apple_unlock(pthread_lock_t *lock) {
    __atomic_store_n(lock, 0, __ATOMIC_RELEASE);
}
#define LOCK_INIT(lock) ((lock) = 0)
#define LOCK(lock) apple_lock(&(lock))
#define UNLOCK(lock) apple_unlock(&(lock))
#define TRY_LOCK(lock) (!__atomic_exchange_n(&(lock), 1, __ATOMIC_ACQUIRE))
extern int __is_threaded;
#endif
