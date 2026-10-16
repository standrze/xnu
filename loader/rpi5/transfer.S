/* SPDX-License-Identifier: BSD-2-Clause
 * Cache-disabled single-primary handoff. See transfer.h for caller obligations.
 * No stack or data memory access, no return path, no secondary release.
 */
.text
.global rpi5_transfer
.type rpi5_transfer,%function
rpi5_transfer:
    msr daifset, #15
    mrs x9, CurrentEL
    cmp x9, #4
    b.ne .Ltransfer_stop
    mrs x9, sctlr_el1
    mov x10, #0x1005
    tst x9, x10
    b.ne .Ltransfer_stop
    tst x0, #7
    b.ne .Ltransfer_stop
    tst x1, #3
    b.ne .Ltransfer_stop
    lsr x9, x0, #40
    cbnz x9, .Ltransfer_stop
    lsr x9, x1, #40
    cbnz x9, .Ltransfer_stop
    mov x9, #0x80000
    cmp x0, x9
    b.lo .Ltransfer_stop
    cmp x1, x9
    b.lo .Ltransfer_stop
    mov x16, x1
    msr spsel, #1
    /* Stop using diagnostic vectors before clearing their private TPIDR state. */
    adrp x9, .Ltransfer_vectors
    add x9, x9, :lo12:.Ltransfer_vectors
    msr vbar_el1, x9
    isb
    msr cntv_ctl_el0, xzr
    msr cntp_ctl_el0, xzr
    msr tpidr_el1, xzr
    msr tpidr_el0, xzr
    msr tpidrro_el0, xzr
    /* Stores were made with D-cache off. Complete them, invalidate stale EL1
     * translations/instructions, then synchronize this executing primary. */
    dsb sy
    tlbi vmalle1
    ic ialluis
    dsb sy
    isb
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    mov x30, xzr
    br x16                   /* XNU start_first_cpu consumes x0 = boot_args PA. */
.Ltransfer_stop:
    wfe
    b .Ltransfer_stop
.size rpi5_transfer, .-rpi5_transfer

/* Terminal vectors are intentionally independent of stack and UART state. */
.balign 2048
.Ltransfer_vectors:
.rept 16
    b .Ltransfer_stop
    .balign 128
.endr
