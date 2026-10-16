/* SPDX-License-Identifier: BSD-2-Clause
 * API and existing XNU counter observation only. Never emit random bytes,
 * hashes of those bytes, seeds, keys, or an entropy-quality claim.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/random.h>
#include <sys/sysctl.h>
#include <unistd.h>

extern int rpi5_packet_pthread_prerequisite(int, char **);

static void erase(void *buffer, size_t size)
{
    volatile unsigned char *p = buffer;
    while (size--) *p++ = 0;
}

static int api_check(void)
{
    unsigned char buffer[256];
    const size_t lengths[] = {0, 1, sizeof(buffer)};
    for (unsigned i = 0; i < sizeof(lengths) / sizeof(lengths[0]); i++) {
        memset(buffer, 0, sizeof(buffer));
        int result = getentropy(buffer, lengths[i]);
        erase(buffer, sizeof(buffer));
        if (result != 0) return 1;
    }
    errno = 0;
    int result = getentropy(buffer, sizeof(buffer) + 1);
    int error = errno;
    erase(buffer, sizeof(buffer));
    if (result != -1 || error != EINVAL) return 2;
    errno = 0;
    result = getentropy((void *)(uintptr_t)1, 1);
    if (result != -1 || errno != EFAULT) return 3;
    return 0;
}

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    int result = rpi5_packet_pthread_prerequisite(argc, argv);
    if (result) return result;
    result = api_check();
    if (result) {
        printf("RPI5XNU:ENTROPY:API FAIL STEP=%d NO_RANDOM_OUTPUT\n", result);
        return 10 + result;
    }
    static const struct {
        const char *name;
        size_t width;
        unsigned failure_counter;
    } queries[] = {
        {"kern.entropy.health.startup_done", sizeof(int), 0},
        {"kern.entropy.health.repetition_count_test.reset_count", sizeof(uint32_t), 0},
        {"kern.entropy.health.repetition_count_test.failure_count", sizeof(uint32_t), 1},
        {"kern.entropy.health.repetition_count_test.max_observation_count", sizeof(uint32_t), 0},
        {"kern.entropy.health.adaptive_proportion_test.reset_count", sizeof(uint32_t), 0},
        {"kern.entropy.health.adaptive_proportion_test.failure_count", sizeof(uint32_t), 1},
        {"kern.entropy.health.adaptive_proportion_test.max_observation_count", sizeof(uint32_t), 0},
        {"kern.entropy.filter.total_sample_count", sizeof(uint64_t), 0},
        {"kern.entropy.filter.accepted_sample_count", sizeof(uint64_t), 0},
        {"kern.entropy.filter.rejected_sample_count", sizeof(uint64_t), 0},
    };
    unsigned unavailable = 0, health_failure = 0;
    for (unsigned i = 0; i < sizeof(queries) / sizeof(queries[0]); i++) {
        union { uint64_t wide; uint32_t small; int boolean; } value = {0};
        size_t size = queries[i].width;
        errno = 0;
        int rc = sysctlbyname(queries[i].name, &value, &size, NULL, 0);
        int error = errno;
        if (rc || size != queries[i].width ||
            (i == 0 && value.boolean != 0 && value.boolean != 1)) {
            unavailable++;
            printf("RPI5XNU:ENTROPY:COUNTER UNAVAILABLE NAME=%s RC=%d ERRNO=%d SIZE=%llu\n",
                queries[i].name, rc, error, (unsigned long long)size);
            continue;
        }
        uint64_t observed = size == sizeof(uint64_t) ? value.wide : value.small;
        if (queries[i].failure_counter && observed) health_failure = 1;
        printf("RPI5XNU:ENTROPY:COUNTER NAME=%s VALUE=%llu\n",
            queries[i].name, (unsigned long long)observed);
    }
    printf("RPI5XNU:ENTROPY:API_OK CALLS=5 COUNTERS=10 UNAVAILABLE=%u HEALTH_FAILURE=%u QUALITY_NOT_PROVEN\n",
        unavailable, health_failure);
    return unavailable ? 20 : health_failure ? 21 : 0;
}
