/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_LOADER_UART_H
#define RPI5_LOADER_UART_H
#include <stdint.h>
#include <stddef.h>

enum rpi5_uart_result { RPI5_UART_OK, RPI5_UART_INVALID, RPI5_UART_DISABLED, RPI5_UART_TIMEOUT };
struct rpi5_uart_snapshot { uint32_t control, flags, integer_divisor, fractional_divisor, line_control; };
/* Read-only raw snapshot, not atomic against firmware changes. Same mapping and
 * exclusive-access preconditions as transmission; no baud/clock inference. */
enum rpi5_uart_result rpi5_uart_snapshot(uintptr_t base, struct rpi5_uart_snapshot *out);
/* Pure standard-PL011 check: exact nominal baud from declared clock, 8N1,
 * transmitter enabled, no loopback or hardware flow control. This does not
 * measure the clock or prove wire timing. FIFO may be enabled or disabled. */
enum rpi5_uart_result rpi5_uart_check_nominal(const struct rpi5_uart_snapshot *state,
    uint32_t declared_hz, uint32_t expected_baud);
/* Exclusive standard PL011, Device mapping through offset 0x48, quiescent
 * receive peer, no firmware console concurrency. Requires interrupts and DMA
 * disabled. Programs only exactly representable rates after bounded TX drain;
 * preserves CR/LCR_H and verifies readback. Does not measure the input clock. */
enum rpi5_uart_result rpi5_uart_set_exact(uintptr_t base, uint32_t declared_hz,
    uint32_t expected_baud, size_t poll_budget);
/* Caller owns exclusive UART access and a valid Device-memory mapping. The
 * polling budget is iterations, not elapsed time. No clock/divisor changes. */
enum rpi5_uart_result rpi5_uart_putc(uintptr_t base, uint8_t byte, size_t poll_budget);
enum rpi5_uart_result rpi5_uart_drain(uintptr_t base, size_t poll_budget);
#endif
