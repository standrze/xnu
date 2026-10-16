/* SPDX-License-Identifier: BSD-2-Clause */
/* Fixed-path, read-only raw Darwin ABI diagnosis. No libc stat adapter. */
#include "runtime.h"
#include <sys/stat.h>
#include <fcntl.h>

_Static_assert(sizeof(struct stat) == 144, "Darwin LP64 stat64 size");
_Static_assert(offsetof(struct stat, st_mode) == 4, "Darwin stat64 mode offset");
_Static_assert(offsetof(struct stat, st_size) == 96, "Darwin stat64 size offset");
_Static_assert(F_DUPFD == 0 && F_GETFD == 1 && F_GETFL == 3, "Darwin fcntl ABI");
_Static_assert(O_RDONLY == 0 && O_NOCTTY == 0x20000, "Darwin open ABI");

struct guarded_stat {
    unsigned char before[16];
    _Alignas(8) unsigned char data[sizeof(struct stat)];
    unsigned char after[16];
};

static void number(long value)
{
    if (value < 0) {
        rt_put(1, "-");
        /* Avoid signed negation overflow, even for a corrupt result. */
        rt_number(1, 0UL - (unsigned long)value);
    } else rt_number(1, (unsigned long)value);
}

static void result(const char *label, long value)
{
    rt_put(1, "STATPROBE:"); rt_put(1, label); rt_put(1, "=");
    number(value); rt_put(1, "\n");
}

static void hex(const unsigned char *data, size_t length)
{
    static const char digits[] = "0123456789abcdef";
    char line[2 * sizeof(struct stat) + 1];
    for (size_t i = 0; i < length; i++) {
        line[2 * i] = digits[data[i] >> 4];
        line[2 * i + 1] = digits[data[i] & 15];
    }
    line[2 * length] = '\n';
    (void)rt_write_all(1, line, 2 * length + 1);
}

static int metadata(long call, long subject, const char *label)
{
    struct guarded_stat value;
    for (size_t i = 0; i < sizeof(value.before); i++) value.before[i] = 0xc3;
    for (size_t i = 0; i < sizeof(value.data); i++) value.data[i] = 0xa5;
    for (size_t i = 0; i < sizeof(value.after); i++) value.after[i] = 0x3c;
    long rc = rt_call(call, subject, (long)value.data, 0, 0, 0, 0);
    result(label, rc);
    /* Raw bytes remain evidence even on failure; A5 means not overwritten. */
    rt_put(1, "STATPROBE:RAW="); hex(value.data, sizeof(value.data));
    int intact = 1;
    for (size_t i = 0; i < sizeof(value.before); i++)
        if (value.before[i] != 0xc3 || value.after[i] != 0x3c) intact = 0;
    result("GUARDS", intact);
    if (!rc) {
        unsigned mode = value.data[4] | ((unsigned)value.data[5] << 8);
        result("MODE", mode);
        result("ISREG", (mode & S_IFMT) == S_IFREG);
        result("ISDIR", (mode & S_IFMT) == S_IFDIR);
    }
    return intact ? 0 : 1;
}

static int open_read(const char *path, int flags)
{
    result("OPEN_FLAGS", flags);
    long fd = rt_open(path, flags);
    result("OPEN", fd);
    if (fd < 0) return 0; /* A reported errno is diagnostic evidence. */
    if (fd > 0x7fffffff) return 1;
    int damaged = metadata(339, fd, "FSTAT64");
    if (damaged) { result("ORIGINAL_CLOSE", rt_close((int)fd)); return 1; }
    result("F_GETFD", rt_call(92, fd, F_GETFD, 0, 0, 0, 0));
    result("F_GETFL", rt_call(92, fd, F_GETFL, 0, 0, 0, 0));
    long duplicate = rt_call(92, fd, F_DUPFD, 10, 0, 0, 0);
    result("F_DUPFD_10", duplicate);
    if (duplicate >= 0) {
        /* Do not read/close a suspicious return that aliases the original. */
        if (duplicate < 10 || duplicate == fd || duplicate > 0x7fffffff) {
            result("BAD_DUPLICATE", 1); damaged = 1;
        } else {
            unsigned char data[16];
            long n = rt_read((int)duplicate, data, sizeof(data));
            result("DUP_READ", n);
            if (n >= 0 && (unsigned long)n <= sizeof(data)) {
                rt_put(1, "STATPROBE:DUP_DATA="); hex(data, (size_t)n);
            } else if (n >= 0) damaged = 1;
            result("DUP_CLOSE", rt_close((int)duplicate));
        }
    }
    unsigned char data[16];
    long n = rt_read((int)fd, data, sizeof(data));
    result("ORIGINAL_READ", n);
    if (n >= 0 && (unsigned long)n <= sizeof(data)) {
        rt_put(1, "STATPROBE:ORIGINAL_DATA="); hex(data, (size_t)n);
    } else if (n >= 0) damaged = 1;
    result("ORIGINAL_CLOSE", rt_close((int)fd));
    return damaged;
}

int statprobe_main(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) { rt_put(2, "usage: statprobe (fixed RAM-root paths only)\n"); return 2; }
    static const char *const paths[] = {
        "/etc/zsh-smoke.zsh", "/etc/motd", "/etc", "/etc/statprobe-missing"
    };
    rt_put(1, "STATPROBE:BEGIN:RAW_DARWIN_STAT64_V1\n");
    int damaged = 0;
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
        const char *path = paths[i];
        rt_put(1, "STATPROBE:PATH="); rt_put(1, path); rt_put(1, "\n");
        result("ACCESS_F_OK", rt_call(33, (long)path, 0, 0, 0, 0, 0));
        result("ACCESS_R_OK", rt_call(33, (long)path, 4, 0, 0, 0, 0));
        damaged |= metadata(338, (long)path, "STAT64");
        if (damaged) break;
        damaged |= metadata(340, (long)path, "LSTAT64");
        if (damaged) break; /* Do not continue after a detected buffer overrun. */
        if (i < 2) {
            damaged |= open_read(path, O_RDONLY);
            if (!damaged) damaged |= open_read(path, O_RDONLY | O_NOCTTY);
        }
        if (damaged) break;
    }
    result("BUFFER_DAMAGE", damaged);
    rt_put(1, "STATPROBE:END:DIAGNOSTIC_ONLY\n");
    /* Zero reports bounded completion, NOT successful file/ABI acceptance. */
    return damaged ? 1 : 0;
}

#ifndef RPI5_STATPROBE_HOST_TEST
_Noreturn void user_start(uintptr_t *stack)
{
    int argc = (int)stack[0];
    rt_exit(statprobe_main(argc, (char **)(stack + 1)));
}
#endif
