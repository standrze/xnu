/* SPDX-License-Identifier: BSD-2-Clause
 * Project-specific static Darwin executable entry and special-result syscall
 * adapters. Numbers and result conventions come from this pinned XNU tree.
 * This is startup/ABI glue, not an Apple Libc replacement.
 */
.text
.p2align 2
.globl _start
_start:
    mov x0, sp
    mov x9, sp
    and x9, x9, #~15
    mov sp, x9
    bl _darwin_static_start
    brk #0

.globl _fork
_fork:
    mov x16, #2
    svc #0x80
    b.cc 1f
    b _cerror_nocancel
1:
    cmp x1, #0
    csel x0, xzr, x0, ne
    ret

.globl _pipe
_pipe:
    stp x19, lr, [sp, #-16]!
    mov x19, x0
    mov x16, #42
    svc #0x80
    b.cs 1f
    stp w0, w1, [x19]
    mov x0, #0
    ldp x19, lr, [sp], #16
    ret
1:
    ldp x19, lr, [sp], #16
    b _cerror_nocancel

.globl _darwin_task_self
_darwin_task_self:
    mov x16, #-28
    svc #0x80
    ret

.globl _mach_timebase_info
_mach_timebase_info:
    mov x16, #-89
    svc #0x80
    ret
