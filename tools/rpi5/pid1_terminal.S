/* Opt-in, freestanding Pi 5 serial terminal. Requires boot arg serial=3.
 * The existing console TTY supplies canonical input, echo, and line editing.
 * This is deliberately separate from the Gate 3 qualification PID 1 image. */

.section __TEXT,__text,regular,pure_instructions
.globl _start
.p2align 2
_start:
#if RPI5_TERMINAL_PROCESS_TRIAL
    /* Save the exec-built argc/argv pointer before aligning the stack. */
    mov x29, sp
#endif
    mov x9, sp
    and x9, x9, #~15
    mov sp, x9

    mov x16, #20                 /* getpid */
    svc #0x80
    b.cs _fatal
    cmp x0, #1
#if RPI5_TERMINAL_PROCESS_TRIAL
    b.ne _process_exec_entry
#else
    b.ne _fatal
#endif

    adrp x0, _console_path@PAGE
    add x0, x0, _console_path@PAGEOFF
    mov x1, #2                  /* O_RDWR */
    mov x2, #0
    mov x16, #5                 /* open */
    svc #0x80
    b.cs _fatal
    mov x19, x0                 /* console fd */

    adrp x1, _banner@PAGE
    add x1, x1, _banner@PAGEOFF
    bl _write_cstr

_prompt:
    adrp x1, _prompt_text@PAGE
    add x1, x1, _prompt_text@PAGEOFF
    bl _write_cstr

    /* Read one canonical line at a time. The bounded buffer cannot overflow;
     * if the line exceeds 126 bytes, drain its remainder before parsing. */
    adrp x20, _line@PAGE
    add x20, x20, _line@PAGEOFF
    mov x21, #0
#if RPI5_TERMINAL_PROCESS_TRIAL
    bl _process_wait_first_input
#endif
_read_line:
    mov x0, x19
    add x1, x20, x21
    mov x2, #1
    mov x16, #3                 /* read */
    svc #0x80
    b.cs _read_error
    cbz x0, _fatal
    ldrb w9, [x20, x21]
    cmp w9, #10                 /* LF */
    b.eq _line_ready
    cmp w9, #13                 /* CR */
    b.eq _line_ready
    add x21, x21, #1
    cmp x21, #127
    b.lo _read_line
_drain_line:
    mov x0, x19
    adrp x1, _discard@PAGE
    add x1, x1, _discard@PAGEOFF
    mov x2, #1
    mov x16, #3
    svc #0x80
    b.cs _read_error
    cbz x0, _fatal
    adrp x9, _discard@PAGE
    add x9, x9, _discard@PAGEOFF
    ldrb w9, [x9]
    cmp w9, #10
    b.ne _drain_line
    adrp x1, _too_long@PAGE
    add x1, x1, _too_long@PAGEOFF
    bl _write_cstr
    b _prompt

_read_error:
    cmp x0, #4                  /* EINTR */
    b.eq _read_line
    b _fatal

_line_ready:
    strb wzr, [x20, x21]
    cbz x21, _prompt

    mov x1, x20
    adrp x2, _help_cmd@PAGE
    add x2, x2, _help_cmd@PAGEOFF
    bl _matches
    cbnz x0, _help
    mov x1, x20
    adrp x2, _status_cmd@PAGE
    add x2, x2, _status_cmd@PAGEOFF
    bl _matches
    cbnz x0, _status
    mov x1, x20
    adrp x2, _ticks_cmd@PAGE
    add x2, x2, _ticks_cmd@PAGEOFF
    bl _matches
    cbnz x0, _ticks
#if RPI5_TERMINAL_PROCESS_TRIAL
    mov x1, x20
    adrp x2, _process_cmd@PAGE
    add x2, x2, _process_cmd@PAGEOFF
    bl _matches
    cbnz x0, _process_trial
#endif

    /* echo followed by one space; bound output by the measured line length. */
    cmp x21, #5
    b.lo _unknown
    ldrb w9, [x20]
    cmp w9, #'e'
    b.ne _unknown
    ldrb w9, [x20, #1]
    cmp w9, #'c'
    b.ne _unknown
    ldrb w9, [x20, #2]
    cmp w9, #'h'
    b.ne _unknown
    ldrb w9, [x20, #3]
    cmp w9, #'o'
    b.ne _unknown
    ldrb w9, [x20, #4]
    cmp w9, #' '
    b.ne _unknown
    adrp x1, _echo_label@PAGE
    add x1, x1, _echo_label@PAGEOFF
    bl _write_cstr
    add x1, x20, #5
    sub x2, x21, #5
    bl _write_all
    adrp x1, _newline@PAGE
    add x1, x1, _newline@PAGEOFF
    mov x2, #1
    bl _write_all
    b _prompt

_help:
    adrp x1, _help_text@PAGE
    add x1, x1, _help_text@PAGEOFF
    bl _write_cstr
    b _prompt
_status:
    mov x16, #20
    svc #0x80
    b.cs _fatal
    cmp x0, #1
    b.ne _fatal
    adrp x1, _status_text@PAGE
    add x1, x1, _status_text@PAGEOFF
    bl _write_cstr
    b _prompt
_ticks:
    /* XNU enables EL0 virtual-counter reads on this ARM profile. This is
     * monotonic diagnostic time, not wall clock or RTC evidence. */
    mrs x27, CNTVCT_EL0
    mrs x28, CNTFRQ_EL0
    adrp x1, _ticks_label@PAGE
    add x1, x1, _ticks_label@PAGEOFF
    bl _write_cstr
    mov x0, x27
    bl _write_hex64
    adrp x1, _freq_label@PAGE
    add x1, x1, _freq_label@PAGEOFF
    bl _write_cstr
    mov x0, x28
    bl _write_hex64
    adrp x1, _crlf@PAGE
    add x1, x1, _crlf@PAGEOFF
    mov x2, #2
    bl _write_all
    b _prompt
_unknown:
    adrp x1, _unknown_text@PAGE
    add x1, x1, _unknown_text@PAGEOFF
    bl _write_cstr
    b _prompt

/* x1=buffer, x2=NUL-terminated literal; result x0=1 if equal. */
_matches:
    ldrb w9, [x1], #1
    ldrb w10, [x2], #1
    cmp w9, w10
    b.ne 1f
    cbnz w9, _matches
    mov x0, #1
    ret
1:
    mov x0, #0
    ret

/* x1=buffer, x2=length. Handle short writes; all strings are bounded. */
_write_cstr:
    mov x2, #0
1:
    ldrb w9, [x1, x2]
    cbz w9, _write_all
    add x2, x2, #1
    b 1b

/* x0=value; emit exactly 16 lowercase hexadecimal digits. */
_write_hex64:
    adrp x24, _hexbuf@PAGE
    add x24, x24, _hexbuf@PAGEOFF
    mov x25, #16
1:
    sub x25, x25, #1
    and x9, x0, #15
    lsr x0, x0, #4
    cmp x9, #10
    b.lo 2f
    add x9, x9, #('a' - 10)
    b 3f
2:
    add x9, x9, #'0'
3:
    strb w9, [x24, x25]
    cbnz x25, 1b
    mov x1, x24
    mov x2, #16
    b _write_all

_write_all:
    cbz x2, 2f
    mov x22, x1
    mov x23, x2
1:
    mov x0, x19
    mov x1, x22
    mov x2, x23
    mov x16, #4                 /* write */
    svc #0x80
    b.cs _fatal
    cbz x0, _fatal
    add x22, x22, x0
    sub x23, x23, x0
    cbnz x23, 1b
2:
    ret

_fatal:
#if RPI5_TERMINAL_PROCESS_TRIAL
    /* Never leave a failed child spinning while PID 1 waits for it. */
    mov x16, #20
    svc #0x80
    cmp x0, #1
    b.eq 1f
    mov x0, #125
    b _process_exit
1:
#endif
    wfe
    b _fatal

.section __TEXT,__cstring,cstring_literals
_console_path: .asciz "/dev/console"
_help_cmd: .asciz "help"
_status_cmd: .asciz "status"
_ticks_cmd: .asciz "ticks"
#if RPI5_TERMINAL_PROCESS_TRIAL
_banner: .asciz "XNU-RPI5 TERMINAL PID1 OK\r\nRPI5XNU:PROC:TRIAL_READY\r\nType help for commands.\r\n"
#else
_banner: .asciz "XNU-RPI5 TERMINAL PID1 OK\r\nType help for commands.\r\n"
#endif
_prompt_text: .asciz "xnu-rpi5> "
#if RPI5_TERMINAL_PROCESS_TRIAL
_help_text: .asciz "help, status, ticks, echo TEXT, process\r\n"
#else
_help_text: .asciz "help, status, ticks, echo TEXT\r\n"
#endif
_status_text: .asciz "PID 1 alive; serial console active.\r\n"
_ticks_label: .asciz "TICKS=0x"
_freq_label: .asciz " FREQ=0x"
_echo_label: .asciz "ECHO: "
_unknown_text: .asciz "Unknown command. Type help.\r\n"
_too_long: .asciz "Input too long (126-byte maximum).\r\n"
/* Every atom in cstring_literals must end in NUL. Without this the linker
 * coalesces the following process command into the newline atom and its
 * symbol points at the leading newline rather than the word "process". */
_newline: .asciz "\n"
_crlf: .asciz "\r\n"

.section __DATA,__bss
.p2align 4
_line: .space 128
_discard: .space 1
_hexbuf: .space 16
