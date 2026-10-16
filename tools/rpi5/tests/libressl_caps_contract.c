/* SPDX-License-Identifier: BSD-2-Clause
 * Actual LibreSSL CPU-capability source, explicit host sysctl double only.
 * This does not qualify the target kernel, instruction dispatch, or entropy.
 */
#include <sys/sysctl.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "crypto_arch.h"

extern void crypto_cpu_caps_init(void);
static const char *names[] = {
    "hw.optional.arm.FEAT_AES", "hw.optional.arm.FEAT_PMULL",
    "hw.optional.arm.FEAT_SHA1", "hw.optional.arm.FEAT_SHA256",
    "hw.optional.arm.FEAT_SHA512", "hw.optional.arm.FEAT_SHA3"
};
static unsigned features, failures, calls, bad;

int rpi5_contract_sysctlbyname(const char *name, void *old, size_t *oldlen,
                             void *newvalue, size_t newlen)
{
    unsigned index = calls++;
    if (index >= 6 || strcmp(name, names[index]) || !old || !oldlen ||
        *oldlen != sizeof(int) || newvalue || newlen || *(int *)old != 0) {
        bad = 1; errno = EINVAL; return -1;
    }
    if (failures & (1U << index)) { errno = ENOENT; return -1; }
    *(int *)old = (features >> index) & 1U;
    return 0;
}

int main(int argc, char **argv)
{
    unsigned cases = 0;
    for (features = 0; features < 64; features++) {
        for (failures = 0; failures < 64; failures++) {
            calls = bad = 0;
            crypto_cpu_caps_aarch64 = UINT64_MAX;
            crypto_cpu_caps_init();
            uint64_t expected = features & ~failures;
            if (argc == 2 && !strcmp(argv[1], "wrong-expectation")) expected ^= 1;
            if (bad || calls != 6 || crypto_cpu_caps_aarch64 != expected) return 33;
            cases++;
        }
    }
    puts("LIBRESSL_CAPS PASS CASES=4096 QUERIES=24576 REAL_SOURCE HOST_SYSCTL_DOUBLE TARGET_NOT_RUN");
    return cases == 4096 ? 0 : 34;
}
