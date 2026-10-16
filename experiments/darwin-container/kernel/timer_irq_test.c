/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>

#define TRUE 1
#define DBG_INTR_TYPE_TIMER 7
static struct cpu_state { int cpu_decrementer; } cpu;
static uint32_t request;
static int pending, clock_calls, eoi_calls, sgi_calls, started, ended, panicked;
static jmp_buf failure;
static uint32_t pe_vz_irq_acknowledge(void) { return request; }
static int ml_get_timer_pending(void) { return pending; }
static void rtclock_intr(int value) { assert(value == TRUE && started == 1 && !ended); clock_calls++; }
static void ml_interrupt_masked_debug_start(void (*handler)(int), int type)
{ assert(handler == rtclock_intr && type == DBG_INTR_TYPE_TIMER); started++; }
static void ml_interrupt_masked_debug_end(void) { ended++; }
static void pe_vz_irq_complete(uint32_t value)
{ assert(value == request && !eoi_calls); assert(!pending || request != 27 || ended == 1); eoi_calls++; }
static void cpu_signal_handler(void) { assert(eoi_calls == 1); sgi_calls++; }
static void panic(const char *format, uint32_t value)
{ (void)format; assert(value == request); panicked++; longjmp(failure, 1); }
static void dispatch(void)
{
    struct cpu_state *cdp = &cpu;
#include "overlay/osfmk/arm64/vz_irq.inc"
}
static void reset(uint32_t value, int is_pending)
{
    request = value; pending = is_pending; cpu.cpu_decrementer = 42;
    clock_calls = eoi_calls = sgi_calls = started = ended = panicked = 0;
}
int main(void)
{
    reset(27, 1); dispatch();
    assert(clock_calls == 1 && eoi_calls == 1 && cpu.cpu_decrementer == -1 && !panicked);
    reset(27, 0); dispatch();
    assert(!clock_calls && eoi_calls == 1 && cpu.cpu_decrementer == 42 && !started && !ended && !panicked);
    reset(1, 0); dispatch(); assert(sgi_calls == 1 && eoi_calls == 1 && !clock_calls);
    for (uint32_t value = 1020; value <= 1023; value++) {
        reset(value, 0); dispatch(); assert(!eoi_calls && !clock_calls && !sgi_calls && !panicked);
    }
    reset(28, 0);
    if (!setjmp(failure)) { dispatch(); assert(0); }
    assert(panicked == 1 && !eoi_calls && !clock_calls);
    return 0;
}
