/* SPDX-License-Identifier: BSD-2-Clause
 * Native adapter for real agent logic. NEVER calls host broadcast kill or reboot.
 * Broadcast is simulated using only fork-registered child identities and their
 * proc_listchildpids descendants, checked by PID and process start timestamp.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <libproc.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/proc_info.h>
#include <sys/select.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../src/runtime.h"
#include "../src/agent_protocol.h"

static char executable[4096];
static int inject, fixture, fail_cleanup, fail_fork;
static unsigned writes, reads;
static struct proc_bsdinfo owned[32];
static size_t owned_count;
static long result(long value) { return value < 0 ? -errno : value; }

static int identity(pid_t pid, struct proc_bsdinfo *info)
{
    return pid > 1 && pid != getpid() &&
        proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, info, sizeof(*info)) == sizeof(*info) && info->pbi_uid == getuid();
}

static int remember(pid_t pid)
{
    struct proc_bsdinfo info;
    if (!identity(pid, &info)) return 0;
    for (size_t i = 0; i < owned_count; i++)
        if (owned[i].pbi_pid == info.pbi_pid && owned[i].pbi_start_tvsec == info.pbi_start_tvsec &&
            owned[i].pbi_start_tvusec == info.pbi_start_tvusec) return 0;
    if (owned_count == sizeof(owned) / sizeof(owned[0])) return -1;
    owned[owned_count++] = info;
    return 0;
}

static int matches(size_t i)
{
    struct proc_bsdinfo info;
    return identity((pid_t)owned[i].pbi_pid, &info) && info.pbi_start_tvsec == owned[i].pbi_start_tvsec &&
        info.pbi_start_tvusec == owned[i].pbi_start_tvusec;
}

static int collect(void)
{
    for (size_t i = 0; i < owned_count; i++) if (matches(i)) {
        pid_t children[32] = {0};
        int bytes = proc_listchildpids((pid_t)owned[i].pbi_pid, children, sizeof(children));
        if (bytes < 0 || bytes >= (int)sizeof(children)) return -1;
        for (size_t j = 0; j < sizeof(children) / sizeof(children[0]); j++)
            if (children[j] && remember(children[j])) return -1;
    }
    return 0;
}

static long owned_broadcast(int signal)
{
    if (collect()) return -E2BIG;
    int found = 0;
    for (size_t i = 0; i < owned_count; i++) if (matches(i)) {
        found = 1;
        if (signal && kill((pid_t)owned[i].pbi_pid, signal) < 0 && errno != ESRCH) return -errno;
    }
    return fail_cleanup && !signal ? 0 : found ? 0 : -ESRCH;
}

long rt_call(long number, long a, long b, long c, long d, long e, long f)
{
    (void)d; (void)f;
    if (number == 37) { assert(a == -1 && !c); return owned_broadcast((int)b); }
    if (number == 48) return result(sigprocmask((int)a, (sigset_t *)b, (sigset_t *)c));
    if (number == 54) {
        assert(!a && c);
        if (b == 0x40487413) { memset((void *)c, 0, 72); return 0; }
        assert(b == 0x80487414);
        const uint64_t *flags = (const uint64_t *)c;
        assert(!flags[0] && !flags[1] && flags[2] == 0x8b00 && !flags[3]);
        assert(((const unsigned char *)c)[48] == 1 && !((const unsigned char *)c)[49]);
        return 0;
    }
    if (number == 55) { assert(a == 8 && !b); _exit(0); } /* guestStopped double only */
    if (number == 59) {
        const char *path = (const char *)a;
        char **arguments = (char **)b;
        /* Sanitized native helpers need no symbolizer or host PATH expansion.
         * This adapter-only option is never present in the guest environment.
         */
        char *native_env[8];
        size_t env_count = 0;
        while (((char **)c)[env_count]) {
            assert(env_count < 6);
            native_env[env_count] = ((char **)c)[env_count]; env_count++;
        }
        native_env[env_count++] = "ASAN_OPTIONS=symbolize=0"; native_env[env_count] = 0;
        if (!strncmp(path, "/bin/agent-", 11)) {
            /* An immediately orphaned native descendant can escape registry
             * discovery. Exercise that fixture only in the exclusive VZ guest.
             */
            if (rt_equal(path, "/bin/agent-orphan")) return -ENOTSUP;
            char *mapped[] = {executable, "--fixture", (char *)rt_basename(path), 0};
            return result(execve(executable, mapped, native_env));
        }
        if (rt_equal(path, "/bin/echo") || rt_equal(path, "/bin/true") || rt_equal(path, "/bin/false") ||
            rt_equal(path, "/bin/cat") || rt_equal(path, "/bin/sleep")) {
            char *mapped[DGA_ARGS_MAX + 3] = {executable, "--utility", (char *)rt_basename(path)};
            size_t i = 1;
            while (arguments[i] && i < DGA_ARGS_MAX) { mapped[i + 2] = arguments[i]; i++; }
            mapped[i + 2] = 0;
            return result(execve(executable, mapped, native_env));
        }
        return result(execve(path, arguments, (char **)c));
    }
    if (number == 7) { if (collect()) return -E2BIG; return result(waitpid((pid_t)a, (int *)b, (int)c)); }
    if (number == 82) return result(setpgid((pid_t)a, (pid_t)b));
    if (number == 92) return result(fcntl((int)a, (int)b, c));
    if (number == 93) {
        fd_set readset, writeset; FD_ZERO(&readset); FD_ZERO(&writeset);
        for (int i = 0; i < a; i++) {
            if (b && (*(uint32_t *)b & (UINT32_C(1) << i))) FD_SET(i, &readset);
            if (c && (*(uint32_t *)c & (UINT32_C(1) << i))) FD_SET(i, &writeset);
        }
        long value = result(select((int)a, b ? &readset : 0, c ? &writeset : 0, 0, (struct timeval *)e));
        if (b) *(uint32_t *)b = 0;
        if (c) *(uint32_t *)c = 0;
        if (value >= 0) for (int i = 0; i < a; i++) {
            if (b && FD_ISSET(i, &readset)) *(uint32_t *)b |= UINT32_C(1) << i;
            if (c && FD_ISSET(i, &writeset)) *(uint32_t *)c |= UINT32_C(1) << i;
        }
        return value;
    }
    if (number == 116) return result(gettimeofday((struct timeval *)a, 0));
    if (number == 147) return result(setsid());
    return -ENOSYS;
}
long rt_fork(void)
{
    if (fail_fork) return -EAGAIN;
    long pid = result(fork());
    if (pid > 0 && remember((pid_t)pid)) abort();
    return pid;
}
long rt_pipe(int fd[2]) { return result(pipe(fd)); }
_Noreturn void rt_exit(int status) { _exit(status); }
long rt_read(int fd, void *data, size_t size)
{
    if (inject && !fixture) {
        reads++;
        if (!(reads % 11)) return -EINTR;
        if (!(reads % 7)) return -EAGAIN;
        if (size > 37) size = 37;
    }
    return result(read(fd, data, size));
}
long rt_write(int fd, const void *data, size_t size)
{
    if (inject && !fixture && fd == 1) {
        writes++;
        if (!(writes % 11)) return -EINTR;
        if (!(writes % 7)) return -EAGAIN;
        if (size > 17) size = 17;
    }
    return result(write(fd, data, size));
}
long rt_open(const char *path, int flags)
{ return result(open(rt_equal(path, "/etc/empty") ? "/dev/null" : path, flags)); }
long rt_close(int fd) { return result(close(fd)); }
long rt_dup2(int from, int to) { return result(dup2(from, to)); }
long rt_chdir(const char *path) { return result(chdir(path)); }
long rt_entries(int fd, void *data, size_t size, long *position)
{ (void)fd; (void)data; (void)size; (void)position; return -ENOSYS; }
long rt_sleep(unsigned seconds) { sleep(seconds); return 0; }
size_t rt_len(const char *text) { return strlen(text); }
int rt_equal(const char *a, const char *b) { return !strcmp(a, b); }
int rt_copy(char *to, size_t size, const char *from)
{ if (strlen(from) >= size) return -1; strcpy(to, from); return 0; }
int rt_write_all(int fd, const void *data, size_t size)
{
    const char *p = data;
    while (size) {
        long n = rt_write(fd, p, size);
        if (n == -EINTR) continue;
        if (n <= 0 || (size_t)n > size) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
void rt_put(int fd, const char *text) { (void)rt_write_all(fd, text, strlen(text)); }
void rt_number(int fd, unsigned long value)
{ char text[32]; snprintf(text, sizeof(text), "%lu", value); rt_put(fd, text); }
void rt_error(const char *operation, long value)
{ rt_put(2, operation); rt_put(2, ": errno "); rt_number(2, (unsigned long)-value); rt_put(2, "\n"); }
const char *rt_basename(const char *path)
{ const char *slash = strrchr(path, '/'); return slash ? slash + 1 : path; }

int main(int argc, char **argv)
{
    assert(realpath(argv[0], executable));
    if (argc >= 2 && rt_equal(argv[1], "--fixture")) {
        fixture = 1;
        if (rt_equal(argv[2], "agent-orphan")) return 77;
        return agent_fixture_main(argv[2], argc - 2, argv + 2);
    }
    if (argc >= 2 && rt_equal(argv[1], "--utility")) {
        fixture = 1;
        return utility_main(argv[2], argc - 2, argv + 2, 0);
    }
    if (argc == 2 && rt_equal(argv[1], "--codec")) {
        char line[DGA_LINE_MAX + 2], encoded[DGA_LINE_MAX];
        while (fgets(line, sizeof(line), stdin)) {
            size_t size = strlen(line);
            if (size && line[size - 1] == '\n') size--;
            while (size && line[size - 1] == '\r') size--;
            struct dga_frame frame;
            const char *error = dga_decode(&frame, line, size);
            if (error) printf("ERROR:%s\n", error);
            else { size = dga_encode(encoded, &frame); assert(size); fwrite(encoded, 1, size, stdout); }
        }
        return 0;
    }
    inject = getenv("DGA_INJECT_SHORT_IO") != 0;
    fail_cleanup = getenv("DGA_FAIL_CLEANUP") != 0;
    fail_fork = getenv("DGA_FAIL_FORK") != 0;
    return agent_main();
}
