/* SPDX-License-Identifier: BSD-2-Clause */
.section __TEXT,__text,regular,pure_instructions
.globl _start, _rt_call, _rt_fork, _rt_pipe
.p2align 2
_start:
    mov x0, sp
    mov x9, sp
    and x9, x9, #~15
    mov sp, x9
    bl _user_start
    mov x0, #127
    mov x16, #1
    svc #0x80
    b .
_rt_call:
    mov x16, x0
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov x3, x4
    mov x4, x5
    mov x5, x6
    svc #0x80
    cneg x0, x0, cs
    ret
_rt_fork:
    mov x16, #2
    svc #0x80
    b.cs 1f
    cmp x1, #0
    csel x0, xzr, x0, ne       /* Darwin raw child flag in x1. */
    ret
1:
    neg x0, x0
    ret
_rt_pipe:
    mov x9, x0
    mov x16, #42
    svc #0x80
    b.cs 1f
    str w0, [x9]
    str w1, [x9, #4]
    mov x0, #0
    ret
1:
    neg x0, x0
    ret
