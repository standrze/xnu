/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit downstream BCM2712/Cortex-A76 capability contract.
 * This is not an implementation of Apple's private APRR service.
 * See Apple's pthread_jit_write_protect_np(3): unsupported reports zero;
 * the original public APIs retain their documented unsupported behavior.
 * Private transition paths are unreachable and trap rather than fake success.
 */
#ifndef RPI5_PTHREAD_BCM2712_CAPABILITIES_H
#define RPI5_PTHREAD_BCM2712_CAPABILITIES_H
#if !defined(RPI5_PTHREAD_NO_PER_THREAD_JIT) || RPI5_PTHREAD_NO_PER_THREAD_JIT != 1
#error This header requires the explicit BCM2712 unsupported-JIT target
#endif
#include <stdbool.h>
static inline bool os_thread_self_restrict_rwx_is_supported(void)
{
    return false;
}
__attribute__((noreturn)) static inline void os_thread_self_restrict_rwx_to_rx(void)
{
    __builtin_trap();
}
__attribute__((noreturn)) static inline void os_thread_self_restrict_rwx_to_rw(void)
{
    __builtin_trap();
}
#endif
