/* SPDX-License-Identifier: BSD-2-Clause
 * Single-primary, non-reentrant seed transaction. Inputs/output/state must
 * lie outside this dedicated stack; caller proves ownership before entry.
 * All called C is compiled -mgeneral-regs-only. Fatal exceptions do not return
 * and therefore do not promise erasure; they must not hand control to XNU.
 */
.text
.global rpi5_firmware_seed_consume_isolated
.type rpi5_firmware_seed_consume_isolated,%function
rpi5_firmware_seed_consume_isolated:
    cmp x1, #64
    b.ne 9f
    cmp x3, #256
    b.ne 9f
    adrp x9, rpi5_seed_stack
    add x9, x9, :lo12:rpi5_seed_stack
    add x10, x9, #4, lsl #12
    /* Reject null, wrapping or scratch-stack-overlapping argument ranges. */
.macro check_external reg, bytes
    cbz \reg, 9f
    adds x11, \reg, #\bytes
    b.cs 9f
    cmp \reg, x10
    b.hs 8f
    cmp x11, x9
    b.hi 9f
8:
.endm
    check_external x0, 64
    check_external x2, 256
    check_external x4, 1
    stp x19, x20, [sp, #-32]!
    str x30, [sp, #16]
    str x18, [sp, #24]
    mov x19, sp
    adrp x9, rpi5_seed_stack
    add x9, x9, :lo12:rpi5_seed_stack
    add x9, x9, #4, lsl #12
    mov sp, x9
    bl rpi5_firmware_seed_consume
    mov w20, w0
    mov sp, x19
    adrp x9, rpi5_seed_stack
    add x9, x9, :lo12:rpi5_seed_stack
    mov x10, #0x4000
1:  str xzr, [x9], #8
    subs x10, x10, #8
    b.ne 1b
    dsb sy
    mov w0, w20
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    mov x4, xzr
    mov x5, xzr
    mov x6, xzr
    mov x7, xzr
    mov x8, xzr
    mov x9, xzr
    mov x10, xzr
    mov x11, xzr
    mov x12, xzr
    mov x13, xzr
    mov x14, xzr
    mov x15, xzr
    mov x16, xzr
    mov x17, xzr
    ldr x30, [sp, #16]
    ldr x18, [sp, #24]
    ldp x19, x20, [sp], #32
    ret
9:  mov w0, #-1
    ret
.size rpi5_firmware_seed_consume_isolated, .-rpi5_firmware_seed_consume_isolated
.section .bss.seed_stack,"aw",%nobits
.balign 16
.global rpi5_seed_stack
rpi5_seed_stack:
    .skip 0x4000
.size rpi5_seed_stack, .-rpi5_seed_stack
