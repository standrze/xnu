/* SPDX-License-Identifier: BSD-2-Clause
 * Filesystem prerequisite, not the final shell. Reuse the proven process
 * lifecycle but exec a distinct /bin/child extent instead of /sbin/launchd.
 */
#define RPI5_RAMROOT_TRIAL 1
#include "pid1_process.S"

.section __TEXT,__text,regular,pure_instructions
.p2align 2
_ramroot_check:
    stp x29, x30, [sp, #-16]!
    mov x25, #-1
    mov x27, #1
    adrp x0, _ramroot_file@PAGE
    add x0, x0, _ramroot_file@PAGEOFF
    mov x1, #0
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cs _ramroot_fail
    mov x25, x0
    mov x27, #2
    mov x0, x25
    mov x1, #16380
    mov x2, #0
    mov x16, #199
    svc #0x80
    b.cs _ramroot_fail
    mov x9, #16380
    cmp x0, x9
    b.ne _ramroot_fail
    mov x27, #3
    mov x0, x25
    adrp x1, _ramroot_buffer@PAGE
    add x1, x1, _ramroot_buffer@PAGEOFF
    mov x2, #8
    mov x16, #3
    svc #0x80
    b.cs _ramroot_fail
    cmp x0, #8
    b.ne _ramroot_fail
    adrp x9, _ramroot_buffer@PAGE
    add x9, x9, _ramroot_buffer@PAGEOFF
    ldr x10, [x9]
    adrp x9, _ramroot_boundary@PAGE
    add x9, x9, _ramroot_boundary@PAGEOFF
    ldr x11, [x9]
    cmp x10, x11
    b.ne _ramroot_fail
    mov x27, #4
    mov x0, x25
    adrp x1, _ramroot_buffer@PAGE
    add x1, x1, _ramroot_buffer@PAGEOFF
    mov x2, #8
    mov x16, #3
    svc #0x80
    b.cs _ramroot_fail
    cbnz x0, _ramroot_fail
    mov x0, x25
    mov x16, #6
    svc #0x80
    mov x25, #-1
    mov x27, #5
    adrp x0, _ramroot_file@PAGE
    add x0, x0, _ramroot_file@PAGEOFF
    mov x1, #1                 /* O_WRONLY must fail EROFS. */
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cc _ramroot_unexpected_open
    cmp x0, #30
    b.ne _ramroot_fail
    mov x27, #6
    adrp x0, _ramroot_missing@PAGE
    add x0, x0, _ramroot_missing@PAGEOFF
    mov x1, #0
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cc _ramroot_unexpected_open
    cmp x0, #2
    b.ne _ramroot_fail
    mov x27, #7
    adrp x0, _ramroot_directory@PAGE
    add x0, x0, _ramroot_directory@PAGEOFF
    mov x1, #0
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cs _ramroot_fail
    mov x25, x0
    mov x27, #8
    bl _ramroot_readdir
    b.cs _ramroot_fail
    cmp x0, #0
    b.le _ramroot_fail
    mov x27, #9
    bl _ramroot_readdir
    b.cs _ramroot_fail
    cbnz x0, _ramroot_fail
    mov x0, x25
    mov x16, #6
    svc #0x80
    adrp x1, _ramroot_pass@PAGE
    add x1, x1, _ramroot_pass@PAGEOFF
    bl _write_cstr
    mov x0, #1
    ldp x29, x30, [sp], #16
    ret
_ramroot_readdir:
    mov x0, x25
    adrp x1, _ramroot_buffer@PAGE
    add x1, x1, _ramroot_buffer@PAGEOFF
    mov x2, #1024
    adrp x3, _ramroot_position@PAGE
    add x3, x3, _ramroot_position@PAGEOFF
    mov x16, #344              /* getdirentries64 */
    svc #0x80
    ret
_ramroot_unexpected_open:
    mov x25, x0
_ramroot_fail:
    mov x28, x0
    adrp x1, _ramroot_fail_text@PAGE
    add x1, x1, _ramroot_fail_text@PAGEOFF
    bl _write_cstr
    mov x0, x27
    bl _write_hex64
    adrp x1, _ramroot_result_text@PAGE
    add x1, x1, _ramroot_result_text@PAGEOFF
    bl _write_cstr
    mov x0, x28
    bl _write_hex64
    adrp x1, _crlf@PAGE
    add x1, x1, _crlf@PAGEOFF
    mov x2, #2
    bl _write_all
    tbnz x25, #63, 1f
    mov x0, x25
    mov x16, #6
    svc #0x80
1:
    mov x0, #0
    ldp x29, x30, [sp], #16
    ret

.section __TEXT,__cstring,cstring_literals
_ramroot_file: .asciz "/etc/boundary"
_ramroot_directory: .asciz "/etc"
_ramroot_missing: .asciz "/etc/not-present"
_ramroot_boundary: .asciz "BOUNDARY"
_ramroot_pass: .asciz "RPI5XNU:RAMROOT:FILES_PASS CROSS_PAGE=1 EOF=1 READONLY=1 MISSING=1 READDIR=1\r\n"
_ramroot_fail_text: .asciz "RPI5XNU:PROC:FAIL STAGE=RAMROOT STEP=0x"
_ramroot_result_text: .asciz " RESULT=0x"
.section __DATA,__bss
.p2align 3
_ramroot_buffer: .space 1024
_ramroot_position: .space 8
