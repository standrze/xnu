/* SPDX-License-Identifier: BSD-2-Clause
 * Private Pi5 candidate only. Included in the actual Apple console owner.
 * Uses the original print buffer and ring; this is not a new output queue.
 * Atomicity is limited to each admitted <=255-byte newline/flush record.
 * Early, interrupt, panic, debugger and post-halt raw output is NOT covered.
 */
#if !defined(RPI5_CONSOLE_RECORDS) || RPI5_CONSOLE_RECORDS != 1 || !defined(ARM64_BOARD_CONFIG_BCM2712)
#error "Explicit Pi5 console-record candidate required"
#endif
#include "osfmk/console/rpi5_console_records.h"
/* Written only by the ordinary ring drainer under its existing flush mutex.
 * Reject recursive kprintf from its UART/video callbacks instead of trying
 * to refill a full ring and wait for the mutex owned by this very thread. */
static uintptr_t rpi5_console_drain_thread;

static int
rpi5_console_record_context(void)
{
    return is_console_initialized() && !disableConsoleOutput && !console_suspended &&
        startup_phase >= STARTUP_SUB_EARLY_BOOT && !kernel_debugger_entry_count &&
        !panic_active() && ml_get_interrupts_enabled() && get_preemption_level() == 0 &&
        !ml_at_interrupt_context() && !pmap_in_ppl() &&
        get_cons_ops_index() == SERIAL_CONS_OPS && current_thread() != THREAD_NULL &&
        __atomic_load_n(&rpi5_console_drain_thread, __ATOMIC_ACQUIRE) != (uintptr_t)current_thread();
}

int
rpi5_console_write_record(const char *bytes, size_t length)
{
    if (!bytes || !length || length >= SERIAL_CONS_BUF_SIZE ||
        (uintptr_t)bytes > UINTPTR_MAX - length || !rpi5_console_record_context()) return 0;
    char record[SERIAL_CONS_BUF_SIZE - 1];
    memcpy(record, bytes, length);
    console_write(record, (int)length);
    return 1;
}

static void
rpi5_console_record_putc(int ch, void *opaque)
{
    struct console_printbuf_state *state = opaque;
    /* Original printbuf truncates a long line unless a global boot flag is
     * changed. Preserve every byte locally without changing that flag: long
     * lines become multiple ordinary records, never claimed atomic. */
    if (state->pos == SERIAL_CONS_BUF_SIZE - 1) console_printbuf_clear(state);
    console_printbuf_putc(ch, state);
}

int
rpi5_console_kprintf_record(const char *format, va_list arguments)
{
    if (!format || !rpi5_console_record_context()) return 0;
    struct console_printbuf_state state;
    console_printbuf_state_init(&state, TRUE, TRUE);
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wformat-nonliteral"
    __doprnt(format, arguments, rpi5_console_record_putc, &state, 16, TRUE);
#pragma clang diagnostic pop
    console_printbuf_clear(&state);
    return 1;
}
