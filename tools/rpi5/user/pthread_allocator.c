/* SPDX-License-Identifier: BSD-2-Clause
 * Private concurrent frontend for the preserved Apple scalable malloc zone.
 * Zone algorithms remain original. Initialization/registration use real
 * acquire/release locks, including before pthread initialization. As with
 * malloc generally, these operations are not async-signal-safe.
 */
#include <malloc/malloc.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>

extern malloc_zone_t *create_scalable_zone(size_t, unsigned);
static malloc_zone_t *default_zone;
static unsigned zone_lock;
unsigned malloc_num_zones;
static malloc_zone_t *zone_storage[16];
malloc_zone_t **malloc_zones = zone_storage;
/* __is_threaded is owned exclusively by the genuine normal libpthread TU. */

static void lock_zones(void)
{
    while (__atomic_exchange_n(&zone_lock, 1, __ATOMIC_ACQUIRE)) {
        while (__atomic_load_n(&zone_lock, __ATOMIC_RELAXED)) {}
    }
}

static void unlock_zones(void)
{
    __atomic_store_n(&zone_lock, 0, __ATOMIC_RELEASE);
}

static int register_locked(malloc_zone_t *zone)
{
    unsigned count = __atomic_load_n(&malloc_num_zones, __ATOMIC_RELAXED);
    unsigned i;
    for (i = 0; i < count; i++) {
        if (zone_storage[i] == zone) return 0;
    }
    if (count == 16) { errno = ENOMEM; return -1; }
    zone_storage[count] = zone;
    __atomic_store_n(&malloc_num_zones, count + 1, __ATOMIC_RELEASE);
    return 0;
}

void malloc_zone_register(malloc_zone_t *zone)
{
    if (!zone) { errno = EINVAL; return; }
    lock_zones();
    (void)register_locked(zone);
    unlock_zones();
}

static malloc_zone_t *get_zone(void)
{
    malloc_zone_t *zone = __atomic_load_n(&default_zone, __ATOMIC_ACQUIRE);
    if (zone) return zone;
    lock_zones();
    zone = __atomic_load_n(&default_zone, __ATOMIC_RELAXED);
    if (!zone) {
        /* Original create_scalable_zone uses VM directly, not this frontend. */
        zone = create_scalable_zone(0, 0);
        if (zone && register_locked(zone) == 0) {
            __atomic_store_n(&default_zone, zone, __ATOMIC_RELEASE);
        } else {
            if (zone) zone->destroy(zone);
            zone = 0;
            errno = ENOMEM;
        }
    }
    unlock_zones();
    return zone;
}

void *malloc(size_t size)
{
    malloc_zone_t *zone = get_zone();
    void *result = zone ? zone->malloc(zone, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}

void *calloc(size_t count, size_t size)
{
    malloc_zone_t *zone;
    void *result;
    if (size && count > SIZE_MAX / size) { errno = ENOMEM; return 0; }
    zone = get_zone();
    result = zone ? zone->calloc(zone, count, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}

void free(void *ptr)
{
    malloc_zone_t *zone = __atomic_load_n(&default_zone, __ATOMIC_ACQUIRE);
    if (ptr && zone) zone->free(zone, ptr);
}

void *realloc(void *ptr, size_t size)
{
    malloc_zone_t *zone;
    void *result;
    if (!ptr) return malloc(size);
    if (!size) { free(ptr); return malloc(1); }
    zone = __atomic_load_n(&default_zone, __ATOMIC_ACQUIRE);
    result = zone ? zone->realloc(zone, ptr, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}

void *valloc(size_t size)
{
    malloc_zone_t *zone = get_zone();
    void *result = zone ? zone->valloc(zone, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}

void malloc_printf(const char *format, ...)
{
    char buffer[1024];
    va_list args;
    int count;
    va_start(args, format);
    count = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    if (count > 0) write(2, buffer, (size_t)count < sizeof(buffer) ?
                        (size_t)count : sizeof(buffer) - 1);
}
