/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOT_UART_H
#define RPI5_BOOT_UART_H
#include <stdint.h>
/* Caller owns an aligned 16-KiB root and the distinct UART-only L2/L3 pair.
 * No RAM entries are copied from the original bootstrap root. */
static inline int
rpi5_boot_uart_root_init(uint64_t *root, uint64_t l2_pa)
{
    if (!root || ((uintptr_t)root & 0x3fff) || !l2_pa ||
        (l2_pa & 0x3fff) || l2_pa >= (1ull << 40)) return 0;
    for (unsigned i = 0; i < 2048; i++) root[i] = 0;
    root[1] = l2_pa | 3;
    return 1;
}
/* Cold-primary diagnostics only, while the dedicated bootstrap Device page
 * remains mapped. No locks, globals, allocation or unbounded polling. */
static inline int
rpi5_boot_uart_mark_at(uintptr_t base, unsigned char stage)
{
    volatile uint32_t *data = (volatile uint32_t *)base;
    volatile uint32_t *flags = (volatile uint32_t *)(base + 0x18);
    unsigned budget = 65535;
    while (*flags & (1u << 5)) {
        if (!--budget) return 0;
    }
    *data = stage;
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#endif
    budget = 65535;
    while (*flags & (1u << 3)) {
        if (!--budget) return 0;
    }
    return 1;
}
#endif
