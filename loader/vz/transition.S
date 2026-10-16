/* SPDX-License-Identifier: BSD-2-Clause
 * EFI identity-mapped EL1 -> cache/MMU-disabled source-built XNU entry.
 * No firmware call is legal after this point. The source-built kernel owns VBAR.
 */
.text
.globl vz_leave_firmware
vz_leave_firmware:
    msr daifset, #15
    /* Clean/invalidate each data/unified cache by set/way, ARMv8 algorithm. */
    mrs x9, clidr_el1
    ubfx x10, x9, #24, #3
    mov x11, #0
1:
    cmp x11, x10
    b.hs 5f
    add x12, x11, x11, lsl #1
    lsr x12, x9, x12
    and x12, x12, #7
    cmp x12, #2
    b.lo 4f
    lsl x12, x11, #1
    msr csselr_el1, x12
    isb
    mrs x13, ccsidr_el1
    and x14, x13, #7
    add x14, x14, #4
    ubfx x15, x13, #3, #10
    clz w16, w15
    ubfx x17, x13, #13, #15
2:
    mov x18, x15
3:
    lsl x19, x18, x16
    lsl x20, x17, x14
    orr x19, x19, x20
    orr x19, x19, x12
    dc cisw, x19
    subs x18, x18, #1
    b.ge 3b
    subs x17, x17, #1
    b.ge 2b
4:
    add x11, x11, #1
    b 1b
5:
    dsb sy
    mrs x9, sctlr_el1
    mov x10, #0x1005
    bic x9, x9, x10
    msr sctlr_el1, x9
    isb
    tlbi vmalle1
    ic iallu
    dsb sy
    isb
    msr cntv_ctl_el0, xzr
    msr cntp_ctl_el0, xzr
    msr tpidr_el1, xzr
    msr tpidr_el0, xzr
    msr tpidrro_el0, xzr
    /* Tail call C at its same identity address, preserving its firmware stack. */
    b vz_after_firmware

.globl vz_enter_xnu
vz_enter_xnu:
    msr daifset, #15
    msr spsel, #1
    mov x16, x1
    mov x1, xzr
    /* VZ-only early trace extension: x2 is the retained physical console
     * record. x0 remains the standard Apple boot-argument pointer. */
    mov x3, xzr
    mov x30, xzr
    dsb sy
    ic iallu
    dsb sy
    isb
    br x16
