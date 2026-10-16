/* Minimal freestanding Darwin arm64 PID 1 for the BCM2712 DEVELOPMENT boot. */
/* BSD syscall numbers are from this tree's bsd/kern/syscalls.master. */

.section __TEXT,__text,regular,pure_instructions
.globl _start
.p2align 2
_start:
    /* The raw Mach-O entry does not pass through dyld/crt startup.  The
     * exec-built argc/pointer area is pointer-aligned, but its total size
     * can leave SP 8 mod 16.  This program does not consume that area, so
     * align SP before any stack access or syscall to meet the arm64 ABI. */
    mov x9, sp
    and x9, x9, #~15
    mov sp, x9

    /* getpid() must identify this process as PID 1. */
    mov x16, #20
    svc #0x80
    b.cs _fatal
    cmp x0, #1
    b.ne _fatal

    /* open("/dev/console", O_RDWR, 0). */
    adrp x0, _console_path@PAGE
    add x0, x0, _console_path@PAGEOFF
    mov x1, #2
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cs _fatal
    mov x19, x0

    /* The exact Gate 2 success marker appears only after PID/console checks. */
    mov x0, x19
    adrp x1, _success@PAGE
    add x1, x1, _success@PAGEOFF
    mov x2, #27
    mov x16, #4
    svc #0x80
    b.cs _fatal
    cmp x0, #27
    b.ne _fatal

_timer_loop:
    /* select(0, NULL, NULL, NULL, {1, 0}) exercises timed syscalls and */
    /* yields the CPU instead of busy-spinning. Reinitialize mutable timeval. */
    sub sp, sp, #16
    mov x9, #1
    str x9, [sp]
    str xzr, [sp, #8]
    mov x0, #0
    mov x1, #0
    mov x2, #0
    mov x3, #0
    mov x4, sp
    mov x16, #93
    svc #0x80
    add sp, sp, #16
    b.cs _timer_error
    cbnz x0, _fatal

    mov x0, x19
    adrp x1, _tick@PAGE
    add x1, x1, _tick@PAGEOFF
    mov x2, #29
    mov x16, #4
    svc #0x80
    b.cs _fatal
    cmp x0, #29
    b.ne _fatal
    b _timer_loop

_timer_error:
    /* Interrupted select is harmless; a different errno is diagnostic. */
    cmp x0, #4
    b.eq _timer_loop
    b _fatal

_fatal:
    /* Keep PID 1 present for serial diagnosis without claiming success. */
    wfe
    b _fatal

.section __TEXT,__cstring,cstring_literals
_console_path:
    .asciz "/dev/console"
_success:
    .asciz "XNU-RPI5 USERSPACE PID1 OK\n"
_tick:
    .asciz "XNU-RPI5 USERSPACE PID1 TICK\n"
