/* SPDX-License-Identifier: BSD-2-Clause */
/* Native POSIX adapter: tests shell logic, not the target syscall ABI/kernel. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../src/runtime.h"
extern char **environ;
static long result(long n) { return n < 0 ? -errno : n; }
long rt_call(long n, long a, long b, long c, long d, long e, long f)
{
    (void)d; (void)e; (void)f;
    if (n == 41) return result(dup((int)a));
    if (n == 59) return result(execve((char *)a, (char **)b, (char **)c));
    /* Never reboot the host in this adapter. Observe the target ABI only. */
    if (n == 55) {
        printf("HOST_STUB:REBOOT:%ld:%ld\n", a, b);
        fflush(stdout);
        return -EPERM;
    }
    return -78;
}
long rt_fork(void) { return result(fork()); }
long rt_pipe(int fd[2]) { return result(pipe(fd)); }
_Noreturn void rt_exit(int n) { _exit(n); }
long rt_read(int fd, void *p, size_t n) { return result(read(fd, p, n)); }
long rt_write(int fd, const void *p, size_t n) { return result(write(fd, p, n)); }
long rt_open(const char *p, int f)
{
    int flags = (f & 3) == RT_RDONLY ? O_RDONLY : (f & 3) == RT_WRONLY ? O_WRONLY : O_RDWR;
    if (f & RT_CREAT) flags |= O_CREAT;
    if (f & RT_TRUNC) flags |= O_TRUNC;
    if (f & RT_APPEND) flags |= O_APPEND;
    return result(open(p, flags, 0644));
}
long rt_close(int fd) { return result(close(fd)); }
long rt_dup2(int a, int b) { return result(dup2(a, b)); }
long rt_wait(long pid, int *s)
{
    long n;
    do { n = result(waitpid((pid_t)pid, s, 0)); } while (n == -EINTR);
    return n;
}
long rt_chdir(const char *p) { return result(chdir(p)); }
long rt_getpid(void) { return getpid(); }
long rt_entries(int fd, void *p, size_t n, long *off)
{ (void)fd; (void)p; (void)n; (void)off; return -78; }
long rt_sleep(unsigned s) { sleep(s); return 0; }
long rt_input_ready(unsigned s)
{
    fd_set f; FD_ZERO(&f); FD_SET(0, &f);
    struct timeval tv = {s, 0};
    return result(select(1, &f, 0, 0, &tv));
}
size_t rt_len(const char *s) { return strlen(s); }
int rt_equal(const char *a, const char *b) { return !strcmp(a, b); }
int rt_copy(char *to, size_t n, const char *from)
{ if (strlen(from) >= n) return -1; strcpy(to, from); return 0; }
int rt_write_all(int fd, const void *data, size_t n)
{
    const char *p = data;
    while (n) {
        long size = rt_write(fd, p, n);
        if (size == -EINTR) continue;
        if (size <= 0) return -1;
        n -= (size_t)size; p += size;
    }
    return 0;
}
void rt_put(int fd, const char *s) { rt_write_all(fd, s, strlen(s)); }
void rt_number(int fd, unsigned long n) { char b[32]; snprintf(b, sizeof(b), "%lu", n); rt_put(fd, b); }
void rt_error(const char *op, long n) { rt_put(2, op); rt_put(2, ": errno "); rt_number(2, (unsigned long)-n); rt_put(2, "\n"); }
const char *rt_basename(const char *s) { const char *p = strrchr(s, '/'); return p ? p + 1 : s; }
int main(int argc, char **argv)
{
    if (argc >= 2 && rt_equal(argv[1], "--utility")) {
        if (argc < 3) return 2;
        return utility_main(argv[2], argc - 2, argv + 2, environ);
    }
    return shell_main(argc, argv, environ);
}
