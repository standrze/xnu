/* SPDX-License-Identifier: BSD-2-Clause */
/* Host callback model only: never substitutes for Pi syscall evidence. */
#include "../user/runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <fcntl.h>

int statprobe_main(int, char **);
static const char *fault;
static unsigned opens, closes, duplicates, calls;
static int held, dupheld, offset;
static int path_allowed(const char *path)
{
    return !strcmp(path, "/etc/zsh-smoke.zsh") || !strcmp(path, "/etc/motd") ||
           !strcmp(path, "/etc") || !strcmp(path, "/etc/statprobe-missing");
}
long rt_call(long number, long a, long b, long c, long d, long e, long f)
{
    calls++;
    assert(!d && !e && !f);
    if (number == 33) {
        assert(!c && (b == 0 || b == 4) && path_allowed((const char *)a));
        return !strcmp((const char *)a, "/etc/statprobe-missing") ? -2 : 0;
    }
    if (number == 338 || number == 339 || number == 340) {
        assert(!c);
        if (number == 339) assert(a == 3 && held);
        else assert(path_allowed((const char *)a));
        if (number != 339 && !strcmp((const char *)a, "/etc/statprobe-missing")) return -2;
        if (!strcmp(fault, "stat-error")) return -5;
        unsigned char *p = (unsigned char *)b;
        memset(p, 0, 144);
        unsigned mode = number != 339 && !strcmp((const char *)a, "/etc") ? S_IFDIR | 0555 : S_IFREG | 0444;
        if (!strcmp(fault, "wrong-mode")) mode = 0444;
        p[4] = (unsigned char)mode; p[5] = (unsigned char)(mode >> 8);
        p[96] = 211;
        if (!strcmp(fault, "overrun")) p[144] = 0;
        if (!strcmp(fault, "fstat-overrun") && number == 339) p[-1] = 0;
        return 0;
    }
    assert(number == 92 && a == 3 && held);
    if (b == F_DUPFD) {
        assert(c == 10 && !dupheld);
        duplicates++;
        if (!strcmp(fault, "dup-error")) return -22;
        if (!strcmp(fault, "dup-alias")) return 3;
        dupheld = 1; return 10;
    }
    assert(!c && (b == F_GETFD || b == F_GETFL));
    return 0;
}
long rt_open(const char *path, int flags)
{
    assert(path_allowed(path) && strcmp(path, "/etc") && strcmp(path, "/etc/statprobe-missing"));
    assert(flags == O_RDONLY || flags == (O_RDONLY | O_NOCTTY));
    assert(!held && !dupheld);
    opens++;
    if (!strcmp(fault, "open-error")) return -6;
    held = 1; offset = 0; return 3;
}
long rt_close(int fd)
{
    if (fd == 10) { assert(dupheld); dupheld = 0; }
    else { assert(fd == 3 && held); held = 0; }
    closes++; return 0;
}
long rt_read(int fd, void *buffer, size_t size)
{
    assert(size == 16 && ((fd == 3 && held) || (fd == 10 && dupheld)));
    if (!strcmp(fault, "read-error")) return -5;
    for (size_t i = 0; i < size; i++) ((unsigned char *)buffer)[i] = (unsigned char)(offset++);
    return (long)size;
}
int rt_write_all(int fd, const void *data, size_t size)
{
    assert(fd == 1 || fd == 2);
    return fwrite(data, 1, size, fd == 1 ? stdout : stderr) == size ? 0 : -1;
}
void rt_put(int fd, const char *value) { (void)rt_write_all(fd, value, strlen(value)); }
void rt_number(int fd, unsigned long value) { assert(fd == 1); printf("%lu", value); }
int main(int argc, char **argv)
{
    assert(argc == 2); fault = argv[1];
    int rc = statprobe_main(!strcmp(fault, "usage") ? 2 : 1, argv);
    assert(!held && !dupheld);
    if (!strcmp(fault, "usage")) assert(!opens && !calls && rc == 2);
    else if (!strcmp(fault, "overrun")) assert(!opens && calls == 3 && rc == 1);
    else if (!strcmp(fault, "fstat-overrun")) assert(opens == 1 && duplicates == 0 && closes == 1 && rc == 1);
    else if (!strcmp(fault, "dup-alias")) assert(opens == 1 && closes == 1 && rc == 1);
    else assert(opens == 4 && rc == 0);
    return rc;
}
