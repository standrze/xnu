/* SPDX-License-Identifier: BSD-2-Clause
 * Appended only to the exact accepted pe_serial TU. Existing Device mapping
 * and provider lifecycle remain authoritative; no new mapper/owner is forged.
 */
#include "pexpert/arm/rpi5_restart_diag_api.h"
#include "osfmk/arm64/rpi5_firmware_fdt_api.h"
#include "loader/rpi5/fdt.h"
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !defined(PL011_UART)
#error "Restart UART requires the exact initialized BCM2712 PL011 provider"
#endif
static int rpi5_restart_diag_uart_live(volatile pl011_registers_t *held,
    uint32_t declared_hz)
{
    if (!uart_initted || !serial_do_transmit || uart_hibernation ||
        !held || pl011_registers != held || gPESF != &pl011_uart_serial_functions ||
        pl011_uart_serial_functions.next != NULL) return 0;
    uint32_t control = held->uartcr.raw, line = held->uartlcr_h.raw;
    uint32_t integer = held->uartibrd.raw, fraction = held->uartfbrd.raw;
    if ((control & 0x101U) != 0x101U || (control & ((1U << 7) | (3U << 14))) ||
        (line & ~0x10U) != 0x60U || !integer || integer > 0xffffU || fraction > 0x3fU ||
        held->uartimsc.raw != 0 || held->uartdmacr.raw != 0) return 0;
    return 4ULL * declared_hz == 115200ULL * (64ULL * integer + fraction);
}
int rpi5_restart_diag_uart(const char *bytes, size_t length)
{
    if (!bytes || !length || length > 256 ||
        (uintptr_t)bytes > UINTPTR_MAX - length) return -1;
    uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
    uint64_t start = __builtin_arm_rsr64("CNTVCT_EL0"), last = start;
    if (frequency < 10 || frequency > UINT32_MAX || start > UINT64_MAX - frequency / 10) return -1;
    uint64_t deadline = start + frequency / 10;
    const void *tree = NULL; size_t size = 0;
    struct rpi5_uart_clocks clocks;
    if (!rpi5_firmware_fdt_view(&tree, &size) || rpi5_fdt_probe_mmio(tree, size) ||
        rpi5_fdt_uart_clocks(tree, size, &clocks)) return -1;
    volatile pl011_registers_t *held = pl011_registers;
    unsigned polls = 0;
    for (size_t at = 0; at <= length;) {
        if (++polls > 1000000U) return -1;
        uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
        if (now < last || now >= deadline ||
            !rpi5_restart_diag_uart_live(held, clocks.uart_hz)) return -1;
        last = now;
        uint32_t flags = held->uartfr.raw;
        if (at == length) {
            if ((flags & 0x88U) == 0x80U) {
                __builtin_arm_dsb(DSB_SY);
                uint64_t done = __builtin_arm_rsr64("CNTVCT_EL0");
                return done >= last && done < deadline &&
                    rpi5_restart_diag_uart_live(held, clocks.uart_hz) ? 0 : -1;
            }
        } else if (!(flags & (1U << 5))) {
            held->uartdr.raw = (uint8_t)bytes[at++];
        }
    }
    return -1;
}
