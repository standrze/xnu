/* SPDX-License-Identifier: BSD-2-Clause
 * Watchdog-only BL33 entry, derived from probe_entry.S. Primary only;
 * all vectors are fatal, no secondary entry, IRQ handler or CPU_OFF call.
 * Requires firmware-loaded linked placement.
 */
.section .text.entry,"ax"
.global _start
.type _start,%function
_start:
    msr daifset, #15
    /* ADR follows the actual executing image; the literal holds the absolute
     * link address. Firmware may relocate a raw image despite kernel_address.
     * Reject that before installing vectors or writing stack/BSS memory. */
    adr x9, _start
    ldr x10, =__probe_start
    cmp x9, x10
    b.ne probe_stop
    mrs x9, CurrentEL
    cmp x9, #8
    b.ne probe_stop
    mrs x10, sctlr_el2
    mov x11, #0x1005
    tst x10, x11              /* Require EL2 MMU, D-cache and I-cache off. */
    b.ne probe_stop
    mov x19, x0              /* Physical runtime FDT pointer from TF-A. */
    adrp x9, probe_vectors
    add x9, x9, :lo12:probe_vectors
    msr vbar_el2, x9
    isb
    /* Before any stack/BSS write, reject an FDT overlapping our entire image.
     * This is still a trusted-firmware readable-pointer contract, not probing.
     * Match the pinned BL31 32-bit pointer and two-2-MiB-block FDT window. */
    tst x19, #7
    b.ne probe_stop
    lsr x9, x19, #32
    cbnz x9, probe_stop
    mov x9, #0x80000
    cmp x19, x9
    b.lo probe_stop
    adrp x12, __probe_start
    add x12, x12, :lo12:__probe_start
    cmp x12, x9
    b.lo probe_stop
    adrp x13, __probe_end
    add x13, x13, :lo12:__probe_end
    and x10, x19, #0xffffffffffe00000
    mov x11, #0x400000
    add x10, x10, x11
    mov x11, #0x100000000
    cmp x10, x11
    csel x10, x10, x11, lo
    add x9, x19, #40
    cmp x9, x10
    b.hi probe_stop
    cmp x19, x13
    b.hs 5f
    cmp x9, x12
    b.hi probe_stop
5:  ldr w9, [x19, #4]
    rev w9, w9              /* FDT totalsize is big endian. */
    cmp w9, #40
    b.lo probe_stop
    add x9, x19, x9
    cmp x9, x10
    b.hi probe_stop
    cmp x19, x13
    b.hs 6f
    cmp x9, x12
    b.hi probe_stop
6:
    msr spsel, #1
    adrp x9, __stack_top
    add x9, x9, :lo12:__stack_top
    mov sp, x9
    adrp x9, __bss_start
    add x9, x9, :lo12:__bss_start
    adrp x10, __bss_end
    add x10, x10, :lo12:__bss_end
1:  cmp x9, x10
    b.hs 2f
    str xzr, [x9], #8
    b 1b
2:  adrp x9, __exception_stack_top
    add x9, x9, :lo12:__exception_stack_top
    msr tpidr_el2, x9
    msr tpidr_el1, x9
    msr tpidrro_el0, xzr   /* Zero identifies the primary fault reporter. */
    adrp x9, probe_report_vectors
    add x9, x9, :lo12:probe_report_vectors
    msr vbar_el2, x9
    isb
    mov x0, x19
    bl probe_main
    adrp x20, probe_el1_entry
    add x20, x20, :lo12:probe_el1_entry
    adrp x21, __stack_top
    add x21, x21, :lo12:__stack_top
probe_enter_el1:
    /* A76 baseline, non-VHE: no stage 2, EL1 AArch64, no IRQ routing. */
    mov x9, #0x80000000
    msr hcr_el2, x9
    isb
    mov x9, #3
    msr cnthctl_el2, x9
    msr cntvoff_el2, xzr
    mov x9, #0x33ff       /* TF-A CPTR_EL2_RES1, no FP trap. */
    msr cptr_el2, x9
    msr mdcr_el2, xzr
    msr hstr_el2, xzr
    msr vttbr_el2, xzr
    mov x9, #0x0800
    movk x9, #0x30d0, lsl #16 /* TF-A SCTLR_EL1_RES1; M/C/I off. */
    msr sctlr_el1, x9
    msr cpacr_el1, xzr   /* Probe uses general registers only. */
    msr cntkctl_el1, xzr
    msr cntv_ctl_el0, xzr
    msr cntp_ctl_el0, xzr
    adrp x9, probe_el1_vectors
    add x9, x9, :lo12:probe_el1_vectors
    msr vbar_el1, x9
    msr sp_el1, x21
    msr elr_el2, x20
    mov x9, #0x3c5       /* DAIF masked, EL1h. */
    msr spsr_el2, x9
    dsb sy
    isb
    eret
probe_el1_entry:
    mov x0, x19
    bl probe_el1_main
probe_stop:
    wfe
    b probe_stop
.size _start, .-_start

/* Used during initialization and while reporting: a nested fault must park. */
.balign 2048
probe_vectors:
.rept 16
    b probe_stop
    .balign 128
.endr

/* Fatal-only handler: no register restoration or exception return is intended.
 * Switch back to parking vectors before touching any memory or the UART. */
.type probe_exception_entry,%function
probe_exception_entry:
    mrs x5, CurrentEL
    cmp x5, #4
    b.eq probe_exception_el1
    adrp x9, probe_vectors
    add x9, x9, :lo12:probe_vectors
    msr vbar_el2, x9
    isb
    mrs x1, esr_el2
    mrs x2, elr_el2
    mrs x3, far_el2
    mrs x4, spsr_el2
    b probe_exception_stack
probe_exception_el1:
    adrp x9, probe_vectors
    add x9, x9, :lo12:probe_vectors
    msr vbar_el1, x9
    isb
    mrs x1, esr_el1
    mrs x2, elr_el1
    mrs x3, far_el1
    mrs x4, spsr_el1
probe_exception_stack:
    msr spsel, #1
    cmp x5, #4
    b.eq 3f
    mrs x9, tpidr_el2
    b 4f
3:  mrs x9, tpidr_el1
4:
    mov sp, x9
    bl probe_exception
    b probe_stop
.size probe_exception_entry, .-probe_exception_entry

.balign 2048
probe_report_vectors:
.set vector_slot, 0
.rept 16
    mov x0, #vector_slot
    b probe_exception_entry
    .balign 128
    .set vector_slot, vector_slot + 1
.endr

.balign 2048
probe_el1_vectors:
.set vector_slot, 0
.rept 16
    mov x0, #vector_slot
    b probe_exception_entry
    .balign 128
    .set vector_slot, vector_slot + 1
.endr
