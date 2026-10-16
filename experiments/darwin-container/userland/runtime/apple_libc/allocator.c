/* Project startup/API adapter around Apple's LP64 scalable_malloc.c.
 * The allocator's allocation, free-list, coalescing and resizing are upstream.
 * This guest is single-threaded; initialization precedes signal installation.
 */
#include <malloc/malloc.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
extern malloc_zone_t *create_scalable_zone(size_t, unsigned);
static malloc_zone_t *default_zone;
unsigned malloc_num_zones;
static malloc_zone_t *zone_storage[16];
malloc_zone_t **malloc_zones = zone_storage;
int __is_threaded;
void malloc_zone_register(malloc_zone_t *zone) {
    if (malloc_num_zones < 16) zone_storage[malloc_num_zones++] = zone;
    else { errno = ENOMEM; }
}
static malloc_zone_t *get_zone(void) {
    if (!default_zone) {
        default_zone = create_scalable_zone(0, 0);
        if (default_zone) malloc_zone_register(default_zone);
        else errno = ENOMEM;
    }
    return default_zone;
}
void *malloc(size_t size) {
    malloc_zone_t *zone = get_zone();
    void *result = zone ? zone->malloc(zone, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}
void *calloc(size_t count, size_t size) {
    malloc_zone_t *zone;
    void *result;
    if (size && count > SIZE_MAX / size) { errno = ENOMEM; return 0; }
    zone = get_zone();
    result = zone ? zone->calloc(zone, count, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}
void free(void *ptr) {
    if (ptr && default_zone) default_zone->free(default_zone, ptr);
}
void *realloc(void *ptr, size_t size) {
    void *result;
    if (!ptr) return malloc(size);
    if (!size) { free(ptr); return malloc(1); }
    result = default_zone->realloc(default_zone, ptr, size);
    if (!result) errno = ENOMEM;
    return result;
}
void *valloc(size_t size) {
    malloc_zone_t *zone = get_zone();
    void *result = zone ? zone->valloc(zone, size) : 0;
    if (!result) errno = ENOMEM;
    return result;
}
void malloc_printf(const char *format, ...) {
    char buffer[1024];
    va_list args;
    int count;
    extern long write(int, const void *, unsigned long);
    va_start(args, format);
    count = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    if (count > 0) write(2, buffer, count < sizeof(buffer) ? count : sizeof(buffer) - 1);
}
