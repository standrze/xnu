/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
extern int rpi5_original_pthread_jit_write_protect_supported_np(void);
extern void rpi5_original_pthread_jit_write_protect_np(int);
extern int rpi5_original_pthread_jit_write_with_callback_np(int (*)(void *), void *);
extern void rpi5_original_pthread_jit_write_freeze_callbacks_np(void);
static int calls;
static int callback(void *ctx) { calls++; return *(int *)ctx; }
int main(void)
{
    int value = 47;
    assert(rpi5_original_pthread_jit_write_protect_supported_np() == 0);
    rpi5_original_pthread_jit_write_protect_np(1);
    rpi5_original_pthread_jit_write_protect_np(0);
    assert(rpi5_original_pthread_jit_write_with_callback_np(callback, &value) == 47);
    rpi5_original_pthread_jit_write_freeze_callbacks_np();
    assert(calls == 1);
    puts("APPLE_JIT_UNSUPPORTED PASS QUERY=0 ORIGINAL_PUBLIC_API_SEMANTICS NO_PROTECTION_CLAIM");
    return 0;
}
