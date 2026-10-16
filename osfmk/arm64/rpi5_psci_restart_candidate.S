/* SPDX-License-Identifier: BSD-2-Clause
 * Mach-O AAPCS64 leaves. Only the three fixed PSCI calls below are possible.
 * x0..x17 are call-clobbered; SMCCC preserves x18..x30. No direct PM MMIO.
 */
.text
.p2align 2
.globl _rpi5_restart_current_el
_rpi5_restart_current_el:
    mrs x0, CurrentEL
    ret

.macro clear_psci_args
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    mov x4, xzr
    mov x5, xzr
    mov x6, xzr
    mov x7, xzr
.endm

.globl _rpi5_restart_psci_version
_rpi5_restart_psci_version:
    clear_psci_args
    mov x0, #0x84000000
    smc #0
    ret

.globl _rpi5_restart_psci_feature
_rpi5_restart_psci_feature:
    clear_psci_args
    mov x0, #10
    movk x0, #0x8400, lsl #16
    mov x1, #9
    movk x1, #0x8400, lsl #16
    smc #0
    ret

.globl _rpi5_restart_psci_reset
_rpi5_restart_psci_reset:
    clear_psci_args
    mov x0, #9
    movk x0, #0x8400, lsl #16
    dsb sy
    isb
    smc #0
    ret
