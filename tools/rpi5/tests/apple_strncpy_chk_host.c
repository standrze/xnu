/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#include "selected-apis.h"
#include "secure.h"

char *fixture___strncpy_chk(char *restrict, char *restrict, size_t, size_t);
static unsigned char buffer[32], before[32];
static int notify_fd, overlap_case;

static void crashed(const char *message)
{
    const char *expected = overlap_case ? "detected source and destination buffer overlap" : "detected buffer overflow";
    if (strcmp(message, expected)) _exit(80);
    if (overlap_case) {
        /* Original overlap validation follows the actual padding write. */
        for (unsigned i = 0; i < 8; i++) if (buffer[i]) _exit(81);
        if (memcmp(buffer + 8, before + 8, sizeof(buffer) - 8)) _exit(82);
    } else if (memcmp(buffer, before, sizeof(buffer))) _exit(83);
    if (write(notify_fd, "C", 1) != 1) _exit(84);
    /* Return to the genuine original caller's trap. */
}

static void fatal_case(unsigned which)
{
    int fds[2], status = 0;
    assert(pipe(fds) == 0);
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        struct rlimit no_core = {0, 0}; assert(setrlimit(RLIMIT_CORE, &no_core) == 0);
        signal(SIGILL, SIG_DFL); signal(SIGTRAP, SIG_DFL);
        close(fds[0]); notify_fd = fds[1]; overlap_case = which == 2;
        memset(buffer, 0xa5, sizeof(buffer));
        if (overlap_case) buffer[0] = 0;
        memcpy(before, buffer, sizeof(buffer));
        os_set_crash_callback(crashed);
        char source[] = "abcdefgh";
        if (which == 0) fixture___strncpy_chk((char *)buffer, source, 8, 4);
        if (which == 1) fixture___strncpy_chk((char *)buffer, source, 1, 0);
        if (which == 2) fixture___strncpy_chk((char *)buffer, (char *)buffer, 8, sizeof(buffer));
        _exit(85);
    }
    close(fds[1]); char marker = 0;
    assert(read(fds[0], &marker, 1) == 1 && marker == 'C'); close(fds[0]);
    assert(waitpid(child, &status, 0) == child && WIFSIGNALED(status));
    assert(WTERMSIG(status) == SIGILL || WTERMSIG(status) == SIGTRAP);
}

static void nonempty_crashed(const char *message)
{
    if (strcmp(message, "detected source and destination buffer overlap")) _exit(87);
    if (!memcmp(buffer, before, sizeof(buffer))) _exit(88);
    const char marker[] = "APPLE_STRNCPY_CHK NONEMPTY_OVERLAP ORIGINAL_FAILURE_AFTER_COPY\n";
    if (write(STDOUT_FILENO, marker, sizeof(marker) - 1) != sizeof(marker) - 1) _exit(89);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "nonempty-overlap")) {
        /* Deliberate original-source negative: overlapping memcpy remains
           undefined behavior. Record whichever real diagnostic occurs. */
        struct rlimit no_core = {0, 0}; assert(setrlimit(RLIMIT_CORE, &no_core) == 0);
        signal(SIGILL, SIG_DFL); signal(SIGTRAP, SIG_DFL);
        memset(buffer, 0xa5, sizeof(buffer)); strcpy((char *)buffer, "abcdefgh");
        memcpy(before, buffer, sizeof(buffer)); os_set_crash_callback(nonempty_crashed);
        fixture___strncpy_chk((char *)buffer + 1, (char *)buffer, 8, 31); return 86;
    }
    unsigned valid = 0, unterminated = 0;
    for (unsigned from = 0; from < 4; from++)
        for (unsigned to = 0; to < 4; to++)
            for (size_t count = 0; count <= 128; count++)
                for (size_t length = 0; length <= 160; length++) {
                    char *source_base = malloc(from + length + 1);
                    unsigned char *dest_base = malloc(to + (count ? count : 1));
                    assert(source_base && dest_base);
                    char *source = source_base + from;
                    unsigned char *dest = dest_base + to;
                    memset(dest_base, 0xa5, to + (count ? count : 1));
                    for (size_t i = 0; i < length; i++) source[i] = (char)('a' + i % 26);
                    source[length] = 0;
                    assert(fixture___strncpy_chk((char *)dest, source, count, count) == (char *)dest);
                    for (size_t i = 0; i < count; i++)
                        assert(dest[i] == (i < length ? (unsigned char)('a' + i % 26) : 0));
                    for (unsigned i = 0; i < to; i++) assert(dest_base[i] == 0xa5);
                    if (!count) assert(dest[0] == 0xa5);
                    for (size_t i = 0; i < length; i++) assert(source[i] == (char)('a' + i % 26));
                    assert(source[length] == 0);
                    free(source_base); free(dest_base); valid++;
                }
    for (size_t count = 0; count <= 128; count++) {
        char *source = malloc(count ? count : 1), *dest = malloc(count ? count : 1);
        assert(source && dest); memset(source, 'x', count); memset(dest, 0xa5, count ? count : 1);
        assert(fixture___strncpy_chk(dest, source, count, count) == dest);
        assert(!memcmp(source, dest, count)); if (!count) assert((unsigned char)dest[0] == 0xa5);
        free(source); free(dest); unterminated++;
    }
    assert(__chk_assert_no_overlap == 1);
    for (unsigned which = 0; which < 3; which++) fatal_case(which);
    assert(valid == 332304 && unterminated == 129);
    puts("APPLE_STRNCPY_CHK PASS VALID=332304 UNTERMINATED=129 OVERFLOW_PREWRITE=2 OVERLAP_AFTERWRITE=1 ORIGINAL_CALLER_TRAP=1");
    return 0;
}
