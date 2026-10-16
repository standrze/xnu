/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PTHREAD_STATIC_ENTRY_CORE_H
#define RPI5_PTHREAD_STATIC_ENTRY_CORE_H
#include <stddef.h>
#include <stdint.h>
struct rpi5_process_vectors {
    int argc;
    char **argv;
    char **envp;
    char **apple;
};

/* Fail atomically; no allocation, errno, TLS, or library calls before Mach init. */
static int rpi5_process_vectors_parse(uintptr_t *stack, size_t words,
                                     struct rpi5_process_vectors *out)
{
    size_t i, argc;
    struct rpi5_process_vectors result;
    if (!stack || !out || words < 4 || stack[0] > 4096) return -1;
    argc = (size_t)stack[0];
    if (argc + 3 >= words || stack[argc + 1] != 0) return -1;
    for (i = 1; i <= argc; i++) if (!stack[i]) return -1;
    result.argc = (int)argc;
    result.argv = (char **)(stack + 1);
    i = argc + 2;
    result.envp = (char **)(stack + i);
    while (i < words && stack[i]) i++;
    if (i == words) return -1;
    result.apple = (char **)(stack + ++i);
    while (i < words && stack[i]) i++;
    if (i == words) return -1;
    *out = result;
    return 0;
}

typedef void (*rpi5_initializer)(void);
static int rpi5_run_initializers(rpi5_initializer *begin, rpi5_initializer *end)
{
    uintptr_t first = (uintptr_t)begin, last = (uintptr_t)end;
    size_t count, i;
    if (last < first || (last-first) % sizeof(*begin)) return -1;
    count = (last-first)/sizeof(*begin);
    if (count > 64 || (count && !begin)) return -1;
    for (i = 0; i < count; i++) if (!begin[i]) return -1;
    for (i = 0; i < count; i++) begin[i]();
    return 0;
}
#endif
