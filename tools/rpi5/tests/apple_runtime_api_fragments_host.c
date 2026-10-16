/* SPDX-License-Identifier: BSD-2-Clause */
#include "selected-apis.h"
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned realloc_calls, free_calls, callback_calls;
static void *input, *returned;
static size_t requested;
static int allocation_errno, callback_fd = -1;
static unsigned char old_block[16], new_block[32];

void *fixture_realloc(void *pointer, size_t size)
{
    if (pointer != input || size != requested) _exit(80);
    realloc_calls++;
    errno = allocation_errno;
    return returned;
}

void fixture_free(void *pointer)
{
    if (pointer != input || !pointer) _exit(81);
    free_calls++;
    errno = EBADF;
}

static void callback(const char *message)
{
    if (strcmp(message, "original crash callback")) _exit(82);
    callback_calls++;
    if (callback_fd >= 0 && write(callback_fd, "C", 1) != 1) _exit(83);
}

static int allocation(void *old, size_t size, void *value, int error, unsigned frees)
{
    input = old; requested = size; returned = value; allocation_errno = error;
    realloc_calls = free_calls = 0; errno = EAGAIN;
    void *result = fixture_reallocf(old, size);
    return result != value || realloc_calls != 1 || free_calls != frees || errno != error;
}

int main(void)
{
    if (allocation(old_block, 32, new_block, EAGAIN, 0) ||
        allocation(old_block, 32, NULL, ENOMEM, 1) ||
        allocation(NULL, 32, NULL, ENOMEM, 0) ||
        allocation(old_block, 0, NULL, 0, 0) ||
        allocation(NULL, 0, new_block, 0, 0) ||
        allocation(old_block, 0, new_block, 0, 0) ||
        allocation(old_block, 16, old_block, 0, 0) ||
        allocation(old_block, 32, NULL, EIO, 1)) return 1;
    os_set_crash_callback(NULL);
    fixture__os_crash("original crash callback");
    if (callback_calls || os_get_crash_callback()) return 2;
    os_set_crash_callback(callback);
    fixture__os_crash("original crash callback");
    if (callback_calls != 1 || os_get_crash_callback() != callback) return 3;
    int descriptors[2];
    if (pipe(descriptors)) return 4;
    pid_t child = fork();
    if (child < 0) return 5;
    if (!child) {
        struct rlimit no_core = {0, 0};
        if (setrlimit(RLIMIT_CORE, &no_core)) _exit(84);
        signal(SIGILL, SIG_DFL); signal(SIGTRAP, SIG_DFL);
        close(descriptors[0]); callback_fd = descriptors[1];
        __os_crash_simple("original crash callback");
        _exit(85);
    }
    close(descriptors[1]);
    char marker = 0;
    if (read(descriptors[0], &marker, 1) != 1 || marker != 'C') return 6;
    close(descriptors[0]);
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFSIGNALED(status) ||
        (WTERMSIG(status) != SIGILL && WTERMSIG(status) != SIGTRAP)) return 7;
    puts("APPLE_RUNTIME_API_FRAGMENTS PASS REALLOCF=8 CRASH_CALLBACK=2 CALLER_TRAP=1 HOST_DOUBLES");
    return 0;
}
