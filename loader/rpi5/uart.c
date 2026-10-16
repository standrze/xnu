/* SPDX-License-Identifier: BSD-2-Clause
 * Freestanding firmware-configured PL011 transmitter, not a boot entry point.
 */
#include "uart.h"

#define UART_DR 0x00u
#define UART_FR 0x18u
#define UART_CR 0x30u
#define FR_BUSY (1u << 3)
#define FR_TXFF (1u << 5)
#define FR_TXFE (1u << 7)
#define CR_UARTEN (1u << 0)
#define CR_TXE (1u << 8)

static uint32_t read_reg(uintptr_t base, unsigned offset)
{
    return *(volatile uint32_t *)(base + offset);
}

enum rpi5_uart_result rpi5_uart_check_nominal(const struct rpi5_uart_snapshot *s,
    uint32_t declared_hz, uint32_t expected_baud)
{
    if (!s || !declared_hz || !expected_baud ||
        !s->integer_divisor || s->integer_divisor > 0xffff ||
        s->fractional_divisor > 0x3f ||
        (s->line_control & ~0x10u) != 0x60u ||
        (s->control & ((1u << 7) | (3u << 14))))
        return RPI5_UART_INVALID;
    if ((s->control & (CR_UARTEN | CR_TXE)) != (CR_UARTEN | CR_TXE))
        return RPI5_UART_DISABLED;
    /* baud = 4 * uartclk / (64 * IBRD + FBRD). Compare the rational
     * value, not rounded baud; uint32 inputs keep both products in uint64. */
    uint64_t divisor = 64ull * s->integer_divisor + s->fractional_divisor;
    return 4ull * declared_hz == (uint64_t)expected_baud * divisor ?
        RPI5_UART_OK : RPI5_UART_INVALID;
}

enum rpi5_uart_result rpi5_uart_snapshot(uintptr_t base, struct rpi5_uart_snapshot *out)
{
    if (!out || !base || (base & 3) || base > UINTPTR_MAX - UART_CR)
        return RPI5_UART_INVALID;
    struct rpi5_uart_snapshot result = {
        read_reg(base, UART_CR), read_reg(base, UART_FR),
        read_reg(base, 0x24), read_reg(base, 0x28), read_reg(base, 0x2c),
    };
    *out = result;
    return RPI5_UART_OK;
}

static enum rpi5_uart_result ready(uintptr_t base, size_t budget)
{
    if (!base || (base & 3) || base > UINTPTR_MAX - UART_CR || !budget) {
        return RPI5_UART_INVALID;
    }
    uint32_t control = read_reg(base, UART_CR);
    if ((control & (CR_UARTEN | CR_TXE)) != (CR_UARTEN | CR_TXE)) {
        return RPI5_UART_DISABLED;
    }
    return RPI5_UART_OK;
}

enum rpi5_uart_result rpi5_uart_putc(uintptr_t base, uint8_t byte, size_t poll_budget)
{
    enum rpi5_uart_result state = ready(base, poll_budget);
    if (state != RPI5_UART_OK) return state;
    while (poll_budget--) {
        if (!(read_reg(base, UART_FR) & FR_TXFF)) {
            *(volatile uint32_t *)(base + UART_DR) = byte;
            return RPI5_UART_OK;
        }
    }
    return RPI5_UART_TIMEOUT;
}

enum rpi5_uart_result rpi5_uart_drain(uintptr_t base, size_t poll_budget)
{
    enum rpi5_uart_result state = ready(base, poll_budget);
    if (state != RPI5_UART_OK) return state;
    while (poll_budget--) {
        uint32_t flags = read_reg(base, UART_FR);
        if ((flags & (FR_BUSY | FR_TXFE)) == FR_TXFE) return RPI5_UART_OK;
    }
    return RPI5_UART_TIMEOUT;
}

enum rpi5_uart_result rpi5_uart_set_exact(uintptr_t base, uint32_t declared_hz,
    uint32_t expected_baud, size_t poll_budget)
{
    if (!base || (base & 3) || base > UINTPTR_MAX - 0x48u ||
        !declared_hz || !expected_baud || !poll_budget)
        return RPI5_UART_INVALID;
    uint64_t scaled = 4ull * declared_hz;
    if (scaled % expected_baud) return RPI5_UART_INVALID;
    uint64_t divisor = scaled / expected_baud;
    if (divisor < 64 || divisor > 0x3fffff) return RPI5_UART_INVALID;
    struct rpi5_uart_snapshot before;
    enum rpi5_uart_result result = rpi5_uart_snapshot(base, &before);
    if (result != RPI5_UART_OK) return result;
    struct rpi5_uart_snapshot desired = before;
    desired.integer_divisor = (uint32_t)(divisor >> 6);
    desired.fractional_divisor = (uint32_t)(divisor & 63);
    result = rpi5_uart_check_nominal(&desired, declared_hz, expected_baud);
    if (result != RPI5_UART_OK) return result;
    /* IMSC and DMACR: do not alter a console with asynchronous users. */
    if (read_reg(base, 0x38) || read_reg(base, 0x48)) return RPI5_UART_INVALID;
    if (before.integer_divisor == desired.integer_divisor &&
        before.fractional_divisor == desired.fractional_divisor)
        return RPI5_UART_OK;
    result = rpi5_uart_drain(base, poll_budget);
    if (result != RPI5_UART_OK) return result;
    *(volatile uint32_t *)(base + UART_CR) = before.control & ~CR_UARTEN;
    (void)read_reg(base, UART_CR);
    *(volatile uint32_t *)(base + 0x24) = desired.integer_divisor;
    *(volatile uint32_t *)(base + 0x28) = desired.fractional_divisor;
    /* LCR_H write latches the combined baud divisor. */
    *(volatile uint32_t *)(base + 0x2c) = before.line_control;
    *(volatile uint32_t *)(base + UART_CR) = before.control;
    struct rpi5_uart_snapshot after;
    result = rpi5_uart_snapshot(base, &after);
    if (result != RPI5_UART_OK) return result;
    if (after.control != before.control || after.line_control != before.line_control)
        return RPI5_UART_INVALID;
    return rpi5_uart_check_nominal(&after, declared_hz, expected_baud);
}
