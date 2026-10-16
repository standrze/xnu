/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"
#include "agent_protocol.h"

static void ignore_term(void)
{
    /* Block TERM without introducing a signal trampoline in static userland. */
    const uint32_t term = UINT32_C(1) << 14;
    if (rt_call(48, 1, (long)&term, 0, 0, 0, 0) < 0) rt_exit(126);
}

static _Noreturn void park(void)
{
    for (;;) rt_sleep(60);
}

int agent_fixture_main(const char *name, int argc, char **argv)
{
    (void)argv;
    if (argc != 1) return 2;
    if (rt_equal(name, "agent-bytes")) {
        unsigned char bytes[256];
        for (unsigned i = 0; i < 256; i++) bytes[i] = (unsigned char)i;
        if (rt_write_all(1, bytes, sizeof(bytes))) return 1;
        for (unsigned i = 0; i < 256; i++) bytes[i] = (unsigned char)(255 - i);
        return rt_write_all(2, bytes, sizeof(bytes)) ? 1 : 0;
    }
    if (rt_equal(name, "agent-flood")) {
        unsigned char bytes[256];
        for (unsigned i = 0; i < 256; i++) bytes[i] = (unsigned char)i;
        for (unsigned i = 0; i < 8192; i++)
            if (rt_write_all(i & 1 ? 2 : 1, bytes, sizeof(bytes))) return 1;
        return 0;
    }
    if (rt_equal(name, "agent-stubborn")) {
        ignore_term(); rt_put(1, "TERM_BLOCKED\n"); park();
    }
    if (rt_equal(name, "agent-escape") || rt_equal(name, "agent-orphan")) {
        ignore_term();
        long child = rt_fork();
        if (child < 0) return 1;
        if (!child) {
            if (rt_call(147, 0, 0, 0, 0, 0, 0) < 0) rt_exit(126);
            rt_put(2, "ESCAPED_DESCENDANT\n"); park();
        }
        rt_put(1, "DESCENDANT_PID="); rt_number(1, (unsigned long)child); rt_put(1, "\n");
        if (rt_equal(name, "agent-orphan")) return 0;
        park();
    }
    return 127;
}
