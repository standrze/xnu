/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"

void *memcpy(void *to, const void *from, size_t n)
{
    unsigned char *d = to;
    const unsigned char *s = from;
    for (size_t i = 0; i < n; i++) d[i] = s[i];
    return to;
}
void *memset(void *to, int value, size_t n)
{
    unsigned char *d = to;
    for (size_t i = 0; i < n; i++) d[i] = (unsigned char)value;
    return to;
}
size_t rt_len(const char *s) { size_t n = 0; while (s[n]) n++; return n; }
int rt_equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
int rt_copy(char *to, size_t capacity, const char *from)
{
    size_t n = rt_len(from);
    if (n >= capacity) return -1;
    memcpy(to, from, n + 1);
    return 0;
}
long rt_read(int fd, void *p, size_t n) { return rt_call(3, fd, (long)p, (long)n, 0, 0, 0); }
long rt_write(int fd, const void *p, size_t n) { return rt_call(4, fd, (long)p, (long)n, 0, 0, 0); }
long rt_open(const char *p, int flags) { return rt_call(5, (long)p, flags, 0644, 0, 0, 0); }
long rt_close(int fd) { return rt_call(6, fd, 0, 0, 0, 0, 0); }
long rt_dup2(int from, int to) { return rt_call(90, from, to, 0, 0, 0, 0); }
long rt_chdir(const char *path) { return rt_call(12, (long)path, 0, 0, 0, 0, 0); }
long rt_getpid(void) { return rt_call(20, 0, 0, 0, 0, 0, 0); }
long rt_entries(int fd, void *p, size_t n, long *position)
{ return rt_call(344, fd, (long)p, (long)n, (long)position, 0, 0); }
long rt_wait(long pid, int *status)
{
    long result;
    do { result = rt_call(7, pid, (long)status, 0, 0, 0, 0); } while (result == -4);
    return result;
}
_Noreturn void rt_exit(int status)
{
    rt_call(1, status, 0, 0, 0, 0, 0);
    for (;;) {}
}
long rt_sleep(unsigned seconds)
{
    long tv[2] = {(long)seconds, 0};
    return rt_call(93, 0, 0, 0, 0, (long)tv, 0);
}
long rt_input_ready(unsigned seconds)
{
    uint32_t readfds = 1;
    long tv[2] = {(long)seconds, 0};
    return rt_call(93, 1, (long)&readfds, 0, 0, (long)tv, 0);
}
int rt_write_all(int fd, const void *data, size_t size)
{
    const char *p = data;
    while (size) {
        long n = rt_write(fd, p, size);
        if (n == -4) continue;
        if (n <= 0 || (unsigned long)n > size) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
void rt_put(int fd, const char *s) { (void)rt_write_all(fd, s, rt_len(s)); }
void rt_number(int fd, unsigned long value)
{
    char number[24]; size_t n = sizeof(number);
    do { number[--n] = (char)('0' + value % 10); value /= 10; } while (value);
    (void)rt_write_all(fd, number + n, sizeof(number) - n);
}
void rt_error(const char *operation, long result)
{
    rt_put(2, operation); rt_put(2, ": errno ");
    rt_number(2, (unsigned long)(result < 0 ? -result : result)); rt_put(2, "\n");
}
const char *rt_basename(const char *path)
{
    const char *name = path;
    for (; *path; path++) if (*path == '/') name = path + 1;
    return name;
}
