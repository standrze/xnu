/* SPDX-License-Identifier: BSD-2-Clause */
/* Only PM_RSTC read, PM_WDOG read/write, barrier and architectural counter.
 * Every peripheral address is fixed here, never supplied by an argument. */
.section .text.recovery_route,"ax"
.global rpi5_recovery_route
.type rpi5_recovery_route,%function
rpi5_recovery_route:
    movz x9, #0x1c
    movk x9, #0x7d20, lsl #16
    movk x9, #0x10, lsl #32
    dsb sy
    ldr w0, [x9]
    dsb sy
    ret
.size rpi5_recovery_route, .-rpi5_recovery_route

.section .text.recovery_countdown,"ax"
.global rpi5_recovery_countdown
.type rpi5_recovery_countdown,%function
rpi5_recovery_countdown:
    movz x9, #0x24
    movk x9, #0x7d20, lsl #16
    movk x9, #0x10, lsl #32
    dsb sy
    ldr w0, [x9]
    dsb sy
    ret
.size rpi5_recovery_countdown, .-rpi5_recovery_countdown

.section .text.recovery_write_countdown,"ax"
.global rpi5_recovery_write_countdown
.type rpi5_recovery_write_countdown,%function
rpi5_recovery_write_countdown:
    movz x9, #0x24
    movk x9, #0x7d20, lsl #16
    movk x9, #0x10, lsl #32
    dsb sy
    str w0, [x9]
    dsb sy
    ret
.size rpi5_recovery_write_countdown, .-rpi5_recovery_write_countdown

.section .text.recovery_order,"ax"
.global rpi5_recovery_order
.type rpi5_recovery_order,%function
rpi5_recovery_order:
    dsb sy
    ret
.size rpi5_recovery_order, .-rpi5_recovery_order

.section .text.recovery_counter,"ax"
.global rpi5_recovery_counter
.type rpi5_recovery_counter,%function
rpi5_recovery_counter:
    isb
    mrs x0, cntvct_el0
    ret
.size rpi5_recovery_counter, .-rpi5_recovery_counter

/* Reuse the original query-only semantics. No CPU_ON/OFF or reset wrapper. */
.section .text.recovery_psci_query,"ax"
.global rpi5_psci_query
.type rpi5_psci_query,%function
rpi5_psci_query:
    mov x2, xzr
    mov x3, xzr
    smc #0
    ret
.size rpi5_psci_query, .-rpi5_psci_query
