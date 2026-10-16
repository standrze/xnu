/* SPDX-License-Identifier: BSD-2-Clause
 * Private Pi5 PL011 leaf only. Exactly one nonblocking acquisition protects
 * the actual FIFO-space check AND DR store. No waiting, video, console, IRQ
 * wait or scheduler callback executes while this guard is held.
 * Panic/debugger output deliberately retains the old raw escape; no record
 * atomicity or FIFO serialization is claimed in those exceptional contexts.
 */
#if !defined(RPI5_CONSOLE_RECORDS) || RPI5_CONSOLE_RECORDS != 1 || !defined(ARM64_BOARD_CONFIG_BCM2712) || !defined(PL011_UART)
#error "Explicit Pi5 PL011 console-record candidate required"
#endif
static unsigned rpi5_console_uart_busy;
static __attribute__((noinline)) int
rpi5_console_uart_try(char c, struct pe_serial_functions *fns)
{
    if (fns != &pl011_uart_serial_functions || panic_active() || kernel_debugger_entry_count) {
        if (!fns->transmit_ready()) return 0;
        fns->transmit_data((uint8_t)c);
        return 1;
    }
    boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
    unsigned expected = 0;
    if (!__atomic_compare_exchange_n(&rpi5_console_uart_busy, &expected, 1, false,
            __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) {
        ml_set_interrupts_enabled(interrupts);
        return 0;
    }
    int sent = 0;
    if (pl011_uart_transmit_ready()) {
        pl011_uart_transmit_data((uint8_t)c);
        sent = 1;
    }
    __atomic_store_n(&rpi5_console_uart_busy, 0, __ATOMIC_RELEASE);
    ml_set_interrupts_enabled(interrupts);
    return sent;
}
