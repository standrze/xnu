/* SPDX-License-Identifier: BSD-2-Clause */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/uio.h>
#include <unistd.h>

void apple_perror_under_test(const char *);

static char captured[256];
static int captured_fd;
static int captured_count;
static int calls;
static int fail_write;
static int strerror_input;

char *fixture_strerror(int value)
{
    strerror_input = value;
    return "permission";
}

ssize_t fixture_writev(int fd, const struct iovec *iov, int count)
{
    size_t used = 0;
    captured_fd = fd;
    captured_count = count;
    calls++;
    captured[0] = '\0';
    for (int i = 0; i < count; i++) {
        if (iov[i].iov_len > sizeof(captured) - used - 1) abort();
        memcpy(captured + used, iov[i].iov_base, iov[i].iov_len);
        used += iov[i].iov_len;
    }
    captured[used] = '\0';
    return fail_write ? -1 : (ssize_t)used;
}

static void reset(void)
{
    memset(captured, 0, sizeof(captured));
    captured_fd = -1;
    captured_count = -1;
    calls = 0;
    fail_write = 0;
    strerror_input = -1;
    errno = 77;
}

static void expect(const char *prefix, const char *output, int count)
{
    reset();
    apple_perror_under_test(prefix);
    if (calls != 1 || captured_fd != STDERR_FILENO || captured_count != count ||
        strerror_input != 77 || strcmp(captured, output) != 0) abort();
}

int main(int argc, char **argv)
{
    if (argc > 1) return 37;
    expect("open", "open: permission\n", 4);
    expect("", "permission\n", 2);
    expect(NULL, "permission\n", 2);
    reset();
    fail_write = 1;
    apple_perror_under_test("write");
    if (calls != 1 || strcmp(captured, "write: permission\n") != 0) abort();
    puts("APPLE_LIBC167_PERROR PASS PREFIX=1 EMPTY=1 NULL=1 WRITEV_FAILURE=1 ABI=NO_FILE");
    return 0;
}
