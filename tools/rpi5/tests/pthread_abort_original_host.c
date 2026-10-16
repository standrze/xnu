/* SPDX-License-Identifier: BSD-2-Clause
 * Simulated syscall endpoints test original wrapper forwarding/fallback only.
 * No host process is killed and this is not a target-kernel abort test.
 */
#include <assert.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/reason.h>
extern void rpi5_original_abort_with_reason(uint32_t, uint64_t, const char *, uint64_t);
extern void rpi5_original_abort_with_payload(uint32_t, uint64_t, void *, uint32_t, const char *, uint64_t);
static jmp_buf finish;
static int fallback, payload_case, first_calls, second_calls;
static char payload[] = "record";
static const char message[] = "test-only original wrapper";
static void check(uint32_t ns, uint64_t code, void *data, uint32_t bytes, const char *text, uint64_t flags)
{
    assert(ns == OS_REASON_LIBSYSTEM && code == 4 && text == message);
    assert(data == (payload_case ? payload : NULL));
    assert(bytes == (payload_case ? sizeof(payload) : 0));
    assert(flags == (second_calls ? OS_REASON_FLAG_ABORT : 0));
    sigset_t blocked;
    assert(!sigprocmask(SIG_SETMASK, NULL, &blocked));
    assert(sigismember(&blocked, SIGABRT) == 0);
}
void rpi5_test_abort(uint32_t ns, uint64_t code, void *data, uint32_t bytes, const char *text, uint64_t flags)
{
    first_calls++;
    check(ns, code, data, bytes, text, flags);
    if (!fallback) longjmp(finish, 1);
}
int rpi5_test_terminate(int pid, uint32_t ns, uint64_t code, void *data, uint32_t bytes, const char *text, uint64_t flags)
{
    second_calls++;
    assert(pid == getpid());
    check(ns, code, data, bytes, text, flags);
    longjmp(finish, 2);
}
int main(void)
{
    for (payload_case = 0; payload_case < 2; payload_case++) {
        for (fallback = 0; fallback < 2; fallback++) {
            first_calls = second_calls = 0;
            sigset_t mask;
            assert(!sigemptyset(&mask) && !sigaddset(&mask, SIGABRT));
            assert(!sigprocmask(SIG_BLOCK, &mask, NULL));
            int outcome = setjmp(finish);
            if (!outcome) {
                if (payload_case) rpi5_original_abort_with_payload(OS_REASON_LIBSYSTEM, 4, payload, sizeof(payload), message, 0);
                else rpi5_original_abort_with_reason(OS_REASON_LIBSYSTEM, 4, message, 0);
                assert(0);
            }
            assert(outcome == (fallback ? 2 : 1));
            assert(first_calls == 1 && second_calls == fallback);
        }
    }
    puts("APPLE_ABORT_WRAPPER PASS CASES=4 SIGNAL_UNMASK FORWARDING FALLBACK SIMULATED_ENDPOINTS_ONLY");
    return 0;
}
