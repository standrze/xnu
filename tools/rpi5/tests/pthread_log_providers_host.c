/* SPDX-License-Identifier: BSD-2-Clause
 * Calls only this process, local unconnected sockets, and the real host clock.
 * Namespaced original providers do not replace the host's pthread runtime.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <libproc.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

extern size_t rpi5_native__platform_strlcpy(char *, const char *, size_t);
extern int rpi5_native_proc_pidinfo(int, int, uint64_t, void *, int);
extern uint64_t rpi5_native_mach_continuous_time(void);
extern uint64_t rpi5_native_mach_absolute_time(void);
extern int rpi5_host_socket(int, int, int);
extern long rpi5_host_sendto(int, const void *, size_t, int, const void *, unsigned);
extern int rpi5_host_close(int);
extern int rpi5_host_fcntl(int, int, long);
extern int rpi5_host_connect(int, const void *, unsigned);
long rpi5_host_cerror(int error) { errno = error; return -1; }

int main(void)
{
    /* Original strlen scans aligned words. Its page-edge behavior is tested
     * separately; leave readable word padding here rather than instrumenting
     * an intentionally partial terminal word as a different strlen contract. */
    char src[288], actual[288], expected[288];
    unsigned copies = 0;
    for (size_t length = 0; length <= 256; length++) {
        memset(src, 'x', sizeof(src)); src[length] = 0;
        for (size_t capacity = 0; capacity <= 257; capacity++) {
            memset(actual, 0x79, sizeof(actual));
            memcpy(expected, actual, sizeof(expected));
            assert(strlcpy(expected + 13, src, capacity) == length);
            assert(rpi5_native__platform_strlcpy(actual + 13, src, capacity) == length);
            assert(!memcmp(actual, expected, sizeof(actual))); copies++;
        }
    }
    unsigned errors = 0, clocks = 0;
    for (unsigned i = 0; i < 1024; i++) {
        errno = 0; assert(rpi5_host_close(-1) == -1 && errno == EBADF); errors++;
        errno = 0; assert(rpi5_host_fcntl(-1, F_GETFL, 0) == -1 && errno == EBADF); errors++;
        errno = 0; assert(rpi5_host_connect(-1, NULL, 0) == -1 && errno == EBADF); errors++;
        errno = 0; assert(rpi5_host_sendto(-1, NULL, 0, 0, NULL, 0) == -1 && errno == EBADF); errors++;
        errno = 0; assert(socket(-1, SOCK_DGRAM, 0) == -1);
        int domain_error = errno;
        errno = 0; assert(rpi5_host_socket(-1, SOCK_DGRAM, 0) == -1 && errno == domain_error); errors++;
        uint64_t before = mach_absolute_time();
        uint64_t value = rpi5_native_mach_absolute_time();
        uint64_t after = mach_absolute_time();
        assert(before <= value && value <= after); clocks++;
        before = mach_continuous_time();
        value = rpi5_native_mach_continuous_time();
        after = mach_continuous_time();
        assert(before <= value && value <= after); clocks++;
    }
    int fd = rpi5_host_socket(AF_UNIX, SOCK_DGRAM, 0);
    assert(fd >= 0);
    assert(rpi5_host_fcntl(fd, F_GETFL, 0) >= 0);
    assert(rpi5_host_close(fd) == 0);
    struct proc_bsdinfo info;
    memset(&info, 0, sizeof(info));
    int count = rpi5_native_proc_pidinfo(getpid(), PROC_PIDTBSDINFO, 0, &info, sizeof(info));
    assert(count == sizeof(info) && info.pbi_pid == (uint32_t)getpid());
    errno = 0;
    assert(rpi5_native_proc_pidinfo(getpid(), 0x7fffffff, 0, &info, sizeof(info)) == 0 && errno == EINVAL);
    printf("APPLE_LOG_PROVIDERS PASS STRLCPY=%u REAL_ERRORS=%u CLOCK_BOUNDS=%u LOCAL_SOCKET=1 SELF_PROC=1 BAD_PROC=1 HOST_ONLY\n", copies, errors, clocks);
    return 0;
}
