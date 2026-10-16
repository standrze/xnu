/* Shell prerequisite trial, not a general shell or a filesystem image.
 * Keep the proven polling console unchanged unless this entry is selected.
 * Syscalls/ABI: bsd/kern/syscalls.master, kern_fork.c, kern_exec.c and
 * osfmk/arm64/status.c:thread_set_child. No dyld or private libc needed. */
#define RPI5_TERMINAL_PROCESS_TRIAL 1
#include "pid1_terminal.S"

.section __TEXT,__text,regular,pure_instructions
.p2align 2
/* SMP UART writers can tear the first banner. Until the first console input,
 * repeat the image-specific readiness marker once per second. Never weaken
 * the host's requirement for an intact marker, and never retry a process
 * command automatically. select sleeps rather than burning an EL0 CPU. */
_process_wait_first_input:
    adrp x9, _process_handshake_done@PAGE
    add x9, x9, _process_handshake_done@PAGEOFF
    ldr w10, [x9]
    cbnz w10, 3f
    cmp x19, #32               /* One 32-bit fd_set word suffices. */
    b.hs _fatal
    stp x29, x30, [sp, #-48]!
1:
    mov w9, #1
    lsl w9, w9, w19
    str w9, [sp, #16]
    mov x9, #1                 /* struct timeval: seconds, microseconds. */
    stp x9, xzr, [sp, #24]
    add x0, x19, #1
    add x1, sp, #16
    mov x2, #0
    mov x3, #0
    add x4, sp, #24
    mov x16, #93               /* select(fd+1, &readfds, NULL, NULL, &tv) */
    svc #0x80
    b.cc 2f
    cmp x0, #4                 /* EINTR does not complete the handshake. */
    b.eq 1b
    b _fatal
2:
    cbnz x0, 4f
    adrp x1, _process_ready_text@PAGE
    add x1, x1, _process_ready_text@PAGEOFF
    bl _write_cstr
    b 1b
4:
    adrp x9, _process_handshake_done@PAGE
    add x9, x9, _process_handshake_done@PAGEOFF
    mov w10, #1
    str w10, [x9]
    ldp x29, x30, [sp], #48
3:
    ret

_process_trial:
#if RPI5_RAMROOT_TRIAL
    bl _ramroot_check
    cbz x0, _prompt
#endif
    adrp x9, _process_cookie@PAGE
    add x9, x9, _process_cookie@PAGEOFF
    mov x10, #0x1234
    str x10, [x9]
    mov x16, #2                 /* fork: child is flagged in x1, not x0. */
    svc #0x80
    b.cs _process_fork_error
    cbnz x1, _process_fork_child
    cmp x0, #1
    b.ls _process_bad_result
    mov x26, x0                /* Parent: exact child PID to reap. */
_process_wait:
    mov x0, x26
    adrp x1, _process_wait_status@PAGE
    add x1, x1, _process_wait_status@PAGEOFF
    mov x2, #0
    mov x3, #0
    mov x16, #7                 /* wait4(child, &status, 0, NULL) */
    svc #0x80
    b.cc 1f
    cmp x0, #4                 /* EINTR: retry the same child only. */
    b.eq _process_wait
    b _process_wait_error
1:
    cmp x0, x26
    b.ne _process_bad_result
    adrp x9, _process_wait_status@PAGE
    add x9, x9, _process_wait_status@PAGEOFF
    ldr w10, [x9]
    mov w11, #0x2a00            /* Normal exit(42), not a signal. */
    cmp w10, w11
    b.ne _process_bad_result
    adrp x9, _process_cookie@PAGE
    add x9, x9, _process_cookie@PAGEOFF
    ldr x10, [x9]
    mov x11, #0x1234            /* Child's write must not affect parent. */
    cmp x10, x11
    b.ne _process_bad_result
    adrp x1, _process_parent_text@PAGE
    add x1, x1, _process_parent_text@PAGEOFF
    bl _write_cstr
    mov x0, x26
    bl _write_hex64
    adrp x1, _process_pass_text@PAGE
    add x1, x1, _process_pass_text@PAGEOFF
    bl _write_cstr
    b _prompt

_process_fork_child:
    /* Exercise copy-on-write, then replace this entire address space. */
    adrp x9, _process_cookie@PAGE
    add x9, x9, _process_cookie@PAGEOFF
    mov x10, #0x5678
    str x10, [x9]
    adrp x1, _process_fork_text@PAGE
    add x1, x1, _process_fork_text@PAGEOFF
    bl _write_cstr
    /* Build argv/envp on the aligned stack. The only executable currently
     * exposed by mockfs is /sbin/launchd: use it, not a fictional /bin/sh. */
    sub sp, sp, #48
    adrp x0, _process_path@PAGE
    add x0, x0, _process_path@PAGEOFF
    adrp x9, _process_arg@PAGE
    add x9, x9, _process_arg@PAGEOFF
    adrp x10, _process_tag@PAGE
    add x10, x10, _process_tag@PAGEOFF
    stp x0, x9, [sp]
    stp x10, xzr, [sp, #16]
    str xzr, [sp, #32]
    mov x1, sp
    add x2, sp, #32
    mov x16, #59                /* execve(path, argv, empty envp) */
    svc #0x80
    /* A successful execve never resumes at this instruction. */
    mov x27, x0
    adrp x1, _process_exec_error_text@PAGE
    add x1, x1, _process_exec_error_text@PAGEOFF
    bl _write_cstr
    mov x0, x27
    bl _write_hex64
    adrp x1, _crlf@PAGE
    add x1, x1, _crlf@PAGEOFF
    mov x2, #2
    bl _write_all
    mov x0, #126
    b _process_exit

_process_exec_entry:
    mov x26, x0                /* getpid at _start returned child PID. */
    cmp x26, #1
    b.ls _process_child_bad
    ldr x9, [x29]              /* kern_exec.c stores argc in a pointer slot. */
    cmp x9, #3
    b.ne _process_child_bad
    ldr x1, [x29, #16]         /* argv[1] */
    cbz x1, _process_child_bad
    adrp x2, _process_arg@PAGE
    add x2, x2, _process_arg@PAGEOFF
    bl _matches
    cbz x0, _process_child_bad
    ldr x1, [x29, #24]         /* argv[2] */
    cbz x1, _process_child_bad
    adrp x2, _process_tag@PAGE
    add x2, x2, _process_tag@PAGEOFF
    bl _matches
    cbz x0, _process_child_bad
    adrp x9, _process_cookie@PAGE
    add x9, x9, _process_cookie@PAGEOFF
    ldr x10, [x9]
    cbnz x10, _process_child_bad /* Exec must supply fresh zero-filled BSS. */
    adrp x0, _console_path@PAGE
    add x0, x0, _console_path@PAGEOFF
    mov x1, #2
    mov x2, #0
    mov x16, #5
    svc #0x80
    b.cs _process_child_bad
    mov x19, x0
    adrp x1, _process_child_text@PAGE
    add x1, x1, _process_child_text@PAGEOFF
    bl _write_cstr
    mov x0, x26
    bl _write_hex64
    adrp x1, _process_child_pass_text@PAGE
    add x1, x1, _process_child_pass_text@PAGEOFF
    bl _write_cstr
    mov x0, #42
    b _process_exit

_process_fork_error:
    adrp x1, _process_fork_error_text@PAGE
    add x1, x1, _process_fork_error_text@PAGEOFF
    b _process_error
_process_wait_error:
    adrp x1, _process_wait_error_text@PAGE
    add x1, x1, _process_wait_error_text@PAGEOFF
_process_error:
    mov x27, x0
    bl _write_cstr
    mov x0, x27
    bl _write_hex64
    adrp x1, _crlf@PAGE
    add x1, x1, _crlf@PAGEOFF
    mov x2, #2
    bl _write_all
    b _prompt
_process_bad_result:
    adrp x1, _process_bad_text@PAGE
    add x1, x1, _process_bad_text@PAGEOFF
    bl _write_cstr
    adrp x9, _process_wait_status@PAGE
    add x9, x9, _process_wait_status@PAGEOFF
    ldr w0, [x9]
    bl _write_hex64
    adrp x1, _crlf@PAGE
    add x1, x1, _crlf@PAGEOFF
    mov x2, #2
    bl _write_all
    b _prompt
_process_child_bad:
    mov x0, #125
_process_exit:
    mov x16, #1
    svc #0x80
    b _process_exit             /* exit must not return. */

.section __TEXT,__cstring,cstring_literals
_process_cmd: .asciz "process"
#if RPI5_RAMROOT_TRIAL
_process_ready_text: .asciz "\r\nRPI5XNU:RAMROOT:READY\r\nRPI5XNU:PROC:TRIAL_READY\r\nxnu-rpi5> "
_process_path: .asciz "/bin/child"
#else
_process_ready_text: .asciz "\r\nRPI5XNU:PROC:TRIAL_READY\r\nxnu-rpi5> "
_process_path: .asciz "/sbin/launchd"
#endif
_process_arg: .asciz "--process-child"
_process_tag: .asciz "RPI5_EXEC_ARG"
_process_fork_text: .asciz "RPI5XNU:PROC:FORK_CHILD\r\n"
_process_child_text: .asciz "RPI5XNU:PROC:EXEC_CHILD PID=0x"
_process_child_pass_text: .asciz " ARG=RPI5_EXEC_ARG BSS_ZERO=1\r\n"
_process_parent_text: .asciz "RPI5XNU:PROC:WAIT_CHILD PID=0x"
_process_pass_text: .asciz " STATUS=0x00002a00 COW=1\r\nRPI5XNU:PROC:PASS\r\n"
_process_fork_error_text: .asciz "RPI5XNU:PROC:FAIL STAGE=FORK ERRNO=0x"
_process_wait_error_text: .asciz "RPI5XNU:PROC:FAIL STAGE=WAIT ERRNO=0x"
_process_exec_error_text: .asciz "RPI5XNU:PROC:FAIL STAGE=EXEC ERRNO=0x"
_process_bad_text: .asciz "RPI5XNU:PROC:FAIL STAGE=RESULT STATUS=0x"

.section __DATA,__bss
.p2align 3
_process_cookie: .space 8
_process_wait_status: .space 4
_process_handshake_done: .space 4
