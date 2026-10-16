/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USER_RUNTIME_H
#define RPI5_USER_RUNTIME_H
#include <stddef.h>
#include <stdint.h>

/* Darwin arm64: syscall errors are returned here as -errno. */
long rt_call(long number, long a, long b, long c, long d, long e, long f);
long rt_fork(void);
long rt_pipe(int descriptors[2]);
_Noreturn void rt_exit(int status);
long rt_read(int fd, void *p, size_t n);
long rt_write(int fd, const void *p, size_t n);
long rt_open(const char *path, int flags);
long rt_close(int fd);
long rt_dup2(int from, int to);
long rt_wait(long pid, int *status);
long rt_chdir(const char *path);
long rt_getpid(void);
long rt_entries(int fd, void *p, size_t n, long *position);
long rt_sleep(unsigned seconds);
long rt_input_ready(unsigned seconds);
size_t rt_len(const char *s);
int rt_equal(const char *a, const char *b);
int rt_copy(char *to, size_t capacity, const char *from);
void rt_put(int fd, const char *text);
void rt_number(int fd, unsigned long number);
void rt_error(const char *operation, long result);
int rt_write_all(int fd, const void *data, size_t size);
const char *rt_basename(const char *path);
int shell_main(int argc, char **argv, char **env);
int utility_main(const char *name, int argc, char **argv, char **env);

#define RT_RDONLY 0
#define RT_WRONLY 1
#define RT_RDWR 2
#define RT_APPEND 8
#define RT_CREAT 512
#define RT_TRUNC 1024
#endif
