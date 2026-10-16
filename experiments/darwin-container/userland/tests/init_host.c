/* SPDX-License-Identifier: BSD-2-Clause
 * Execute the real PID1 control flow with syscall/fork/sleep test doubles.
 * No host signal mask, child process, exec or shutdown syscall is changed.
 */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/runtime.h"

extern _Noreturn void user_start(uintptr_t *stack);
static jmp_buf finished;
static const uint32_t term = UINT32_C(1) << 14;
static const uint32_t initial_mask = UINT32_C(1) << 9;
static uint32_t current_mask, pending;
static int mode, forks, waits, restores, respawns, shutdown_seen, exit_seen;
static int agent_stopped;

long rt_call(long number, long a, long b, long c, long d, long e, long f)
{
    (void)d; (void)e; (void)f;
    if (number == 48 && a == 1) {
        assert(*(const uint32_t *)b == term);
        *(uint32_t *)c = current_mask;
        current_mask |= *(const uint32_t *)b;
        return 0;
    }
    if (number == 48 && a == 3) {
        assert(!c);
        current_mask = *(const uint32_t *)b;
        restores++;
        return 0;
    }
    if (number == 52) { *(uint32_t *)a = pending; return 0; }
    if (number == 59) {
        assert(mode == 2 && restores == 1 && current_mask == initial_mask);
        assert((current_mask & term) == 0);
#ifdef DARWIN_AGENT_INIT
        assert(strcmp((const char *)a, "/sbin/darwin-agent") == 0);
#else
        assert(strcmp((const char *)a, "/bin/sh") == 0);
#endif
        longjmp(finished, 2);
    }
    abort();
}
long rt_getpid(void) { return 1; }
long rt_open(const char *path, int flags) { assert(strcmp(path, "/dev/console") == 0 && flags == RT_RDWR); return 3; }
long rt_dup2(int from, int to) { assert(from == 3 && to >= 0 && to <= 2); return to; }
long rt_close(int fd) { assert(fd == 3); return 0; }
long rt_fork(void)
{
    assert((current_mask & term) != 0 && !shutdown_seen && forks < 2);
    forks++;
    return mode == 2 ? 0 : 2;
}
long rt_wait(long pid, int *status)
{
    assert(pid == -1 && !shutdown_seen);
    *status = 0;
    waits++;
    if (mode != 3 || waits == 2) pending |= term;
    return 2;
}
long rt_sleep(unsigned seconds)
{
    if (agent_stopped) {
        assert(mode == 3 && seconds == 60 && forks == 1 && !respawns && !exit_seen);
        longjmp(finished, 3);
    }
    if (shutdown_seen) {
        assert(seconds == 60 && !exit_seen);
        assert(forks == (mode == 1 ? 0 : mode == 3 ? 2 : 1));
        assert(respawns == (mode == 3 ? 1 : 0));
        longjmp(finished, 1);
    }
    assert(mode == 3 && seconds == 1);
    return 0;
}
void rt_put(int fd, const char *text)
{
    assert(fd == 1);
    if (strcmp(text, "DARWIN:INIT:SHUTDOWN\n") == 0) shutdown_seen++;
    if (strcmp(text, "DARWIN:INIT:RESPAWN\n") == 0) { assert(!shutdown_seen); respawns++; }
    if (strcmp(text, "DARWIN:INIT:AGENT_STOPPED\n") == 0) agent_stopped++;
}
void rt_number(int fd, unsigned long number) { assert(fd == 1 && number == 2); }
void rt_error(const char *operation, long result) { (void)operation; (void)result; abort(); }
_Noreturn void rt_exit(int status) { (void)status; exit_seen = 1; abort(); }
const char *rt_basename(const char *path) { return path; }
int rt_equal(const char *a, const char *b) { return strcmp(a, b) == 0; }
int shell_main(int argc, char **argv, char **env) { (void)argc; (void)argv; (void)env; abort(); }
int utility_main(const char *name, int argc, char **argv, char **env)
{ (void)name; (void)argc; (void)argv; (void)env; abort(); }
#ifdef DARWIN_AGENT_INIT
int agent_main(void) { abort(); }
int agent_fixture_main(const char *name, int argc, char **argv)
{ (void)name; (void)argc; (void)argv; abort(); }
#endif

int main(int argc, char **argv)
{
    assert(argc == 2);
    mode = atoi(argv[1]);
    assert(mode >= 0 && mode <= 3);
    current_mask = initial_mask;
    if (mode == 1) pending = term;
    int outcome = setjmp(finished);
    if (!outcome) user_start(NULL);
#ifdef DARWIN_AGENT_INIT
    assert(outcome == (mode == 2 ? 2 : mode == 3 ? 3 : 1));
#else
    assert(outcome == (mode == 2 ? 2 : 1));
#endif
    assert(!exit_seen);
    puts("INIT_PASS");
    return 0;
}
