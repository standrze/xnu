/* SPDX-License-Identifier: BSD-2-Clause
 * Project own-process timing adapter. Relative waiting is performed by the
 * kernel select syscall; interrupted remainder uses actual Mach uptime ticks
 * and the kernel's timebase, not wall time or a fabricated successful sleep.
 */
#include <sys/select.h>
#include <sys/time.h>
#include <mach/mach_time.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <time.h>

extern int __gettimeofday_with_mach(struct timeval *, struct timezone *, uint64_t *);

int nanosleep(const struct timespec *requested, struct timespec *remaining)
{
    if (!requested || requested->tv_sec < 0 || requested->tv_nsec < 0 ||
        requested->tv_nsec >= 1000000000L ||
        (uint64_t)requested->tv_sec > UINT64_MAX / 1000000000 - 1) {
        errno = EINVAL; return -1;
    }
    struct timeval timeout = {requested->tv_sec, (int)((requested->tv_nsec + 999) / 1000)};
    if (timeout.tv_usec == 1000000) { timeout.tv_sec++; timeout.tv_usec = 0; }
    uint64_t begin = 0, end = 0;
    struct timeval wall;
    mach_timebase_info_data_t scale;
    if (remaining && (mach_timebase_info(&scale) != 0 || !scale.denom ||
                      __gettimeofday_with_mach(&wall, 0, &begin) < 0))
        return -1;
    int result = select(0, 0, 0, 0, &timeout);
    if (result == 0) {
        if (remaining) remaining->tv_sec = remaining->tv_nsec = 0;
        return 0;
    }
    int saved = errno;
    if (remaining && saved == EINTR) {
        if (__gettimeofday_with_mach(&wall, 0, &end) < 0) return -1;
        uint64_t ticks = end - begin;
        uint64_t elapsed = scale.numer && ticks > UINT64_MAX / scale.numer
            ? UINT64_MAX : ticks * scale.numer / scale.denom;
        uint64_t total = (uint64_t)requested->tv_sec * 1000000000 + requested->tv_nsec;
        total = elapsed < total ? total - elapsed : 0;
        remaining->tv_sec = (time_t)(total / 1000000000);
        remaining->tv_nsec = (long)(total % 1000000000);
    }
    errno = saved;
    return -1;
}
