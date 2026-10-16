/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <mach/mach.h>
#include <mach/host_info.h>
#include <stdio.h>
#include <string.h>

extern kern_return_t rpi5_native_host_info(host_t, host_flavor_t, host_info_t,
                                         mach_msg_type_number_t *);

int main(void)
{
    host_t host = mach_host_self();
    assert(MACH_PORT_VALID(host));
    const host_flavor_t flavors[] = { HOST_BASIC_INFO, HOST_PRIORITY_INFO, -1, 0x7fffffff };
    unsigned cases = 0;
    for (unsigned port = 0; port < 2; port++) {
        for (unsigned f = 0; f < sizeof(flavors) / sizeof(flavors[0]); f++) {
            for (unsigned capacity = 0; capacity < 3; capacity++) {
                integer_t actual[HOST_INFO_MAX], reference[HOST_INFO_MAX];
                memset(actual, 0xa5, sizeof(actual));
                memset(reference, 0xa5, sizeof(reference));
                mach_msg_type_number_t n = capacity == 0 ? 0 : capacity == 1 ? 1 : HOST_INFO_MAX;
                mach_msg_type_number_t nref = n;
                host_t target = port ? MACH_PORT_NULL : host;
                kern_return_t a = rpi5_native_host_info(target, flavors[f], actual, &n);
                kern_return_t r = host_info(target, flavors[f], reference, &nref);
                assert(a == r && n == nref);
                assert(!memcmp(actual, reference, sizeof(actual)));
                if (!port && capacity == 2 && f < 2) assert(a == KERN_SUCCESS);
                if (port || f >= 2) assert(a != KERN_SUCCESS);
                cases++;
            }
        }
    }
    assert(mach_port_deallocate(mach_task_self(), host) == KERN_SUCCESS);
    printf("APPLE_MIG_HOST_INFO PASS REAL_KERNEL_CASES=%u ORIGINAL_GENERATED_USER VALID_AND_FAILURE HOST_ONLY\n", cases);
    return 0;
}
