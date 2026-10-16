
.macro ENTRY
 .align 2
 .globl _$0
 _$0 :
.endmacro
.macro ENTRY2
 .align 2
 .globl _$0
 .globl _$1
 _$0 :
 _$1 :
.endmacro
.macro READ_THREAD
 mrs $0, TPIDR_EL1
.endmacro
.macro BRANCH_EXTERN
 b _$0
.endmacro
.macro CALL_EXTERN
 bl _$0
.endmacro
.macro MOV64
 movk $0, #((($1) >> 48) & 0x000000000000FFFF), lsl #48
 movk $0, #((($1) >> 32) & 0x000000000000FFFF), lsl #32
 movk $0, #((($1) >> 16) & 0x000000000000FFFF), lsl #16
 movk $0, #((($1) >> 00) & 0x000000000000FFFF), lsl #00
.endmacro
.macro MOV32
 movz $0, #((($1) >> 16) & 0x000000000000FFFF), lsl #16
 movk $0, #((($1) >> 00) & 0x000000000000FFFF), lsl #00
.endmacro
.macro ARM64_STACK_PROLOG
.endmacro
.macro ARM64_STACK_EPILOG
 ret
.endmacro
.macro ARM64_STACK_PROLOG_ENH
 ARM64_STACK_PROLOG
.endmacro
.macro ARM64_STACK_EPILOG_ENH label
 ARM64_STACK_EPILOG
.endmacro
.text 
 .align 2 
 .globl __exit 
 __exit: 
 mov x16, #(1) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _read 
 _read: 
 mov x16, #(3) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _write 
 _write: 
 mov x16, #(4) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _darwin_open 
 _darwin_open: 
 mov x16, #(5) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _close 
 _close: 
 mov x16, #(6) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _wait4 
 _wait4: 
 mov x16, #(7) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _link 
 _link: 
 mov x16, #(9) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _unlink 
 _unlink: 
 mov x16, #(10) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _chdir 
 _chdir: 
 mov x16, #(12) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _fchdir 
 _fchdir: 
 mov x16, #(13) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _chmod 
 _chmod: 
 mov x16, #(15) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _chown 
 _chown: 
 mov x16, #(16) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getpid 
 _getpid: 
 mov x16, #(20) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getppid 
 _getppid: 
 mov x16, #(39) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getuid 
 _getuid: 
 mov x16, #(24) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _geteuid 
 _geteuid: 
 mov x16, #(25) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getgid 
 _getgid: 
 mov x16, #(47) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getegid 
 _getegid: 
 mov x16, #(43) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _access 
 _access: 
 mov x16, #(33) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___kill 
 ___kill: 
 mov x16, #(37) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setuid 
 _setuid: 
 mov x16, #(23) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setgid 
 _setgid: 
 mov x16, #(181) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getpgrp 
 _getpgrp: 
 mov x16, #(81) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setpgid 
 _setpgid: 
 mov x16, #(82) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _dup 
 _dup: 
 mov x16, #(41) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _dup2 
 _dup2: 
 mov x16, #(90) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _umask 
 _umask: 
 mov x16, #(60) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _darwin_ioctl 
 _darwin_ioctl: 
 mov x16, #(54) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _darwin_fcntl 
 _darwin_fcntl: 
 mov x16, #(92) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _execve 
 _execve: 
 mov x16, #(59) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _readlink 
 _readlink: 
 mov x16, #(58) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _symlink 
 _symlink: 
 mov x16, #(57) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _rename 
 _rename: 
 mov x16, #(128) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _lseek 
 _lseek: 
 mov x16, #(199) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _fchmod 
 _fchmod: 
 mov x16, #(124) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _fchown 
 _fchown: 
 mov x16, #(123) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _select 
 _select: 
 mov x16, #(93) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getrusage 
 _getrusage: 
 mov x16, #(117) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getrlimit 
 _getrlimit: 
 mov x16, #(194) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setrlimit 
 _setrlimit: 
 mov x16, #(195) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setreuid 
 _setreuid: 
 mov x16, #(126) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setregid 
 _setregid: 
 mov x16, #(127) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _seteuid 
 _seteuid: 
 mov x16, #(183) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setegid 
 _setegid: 
 mov x16, #(182) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _sigprocmask 
 _sigprocmask: 
 mov x16, #(48) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___sigsuspend_nocancel 
 ___sigsuspend_nocancel: 
 mov x16, #(111) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___sigaction 
 ___sigaction: 
 mov x16, #(46) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___sigreturn 
 ___sigreturn: 
 mov x16, #(184) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___sigaltstack 
 ___sigaltstack: 
 mov x16, #(53) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___mmap 
 ___mmap: 
 mov x16, #(197) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl ___munmap 
 ___munmap: 
 mov x16, #(73) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _mprotect 
 _mprotect: 
 mov x16, #(74) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _sysctl 
 _sysctl: 
 mov x16, #(202) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getdirentries64 
 _getdirentries64: 
 mov x16, #(344) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _apple_getdirentries64 
 _apple_getdirentries64: 
 mov x16, #(344) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _stat 
 _stat: 
 mov x16, #(338) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _fstat 
 _fstat: 
 mov x16, #(339) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _lstat 
 _lstat: 
 mov x16, #(340) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _fstatfs 
 _fstatfs: 
 mov x16, #(346) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _issetugid 
 _issetugid: 
 mov x16, #(327) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getentropy 
 _getentropy: 
 mov x16, #(500) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _csops 
 _csops: 
 mov x16, #(169) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setitimer 
 _setitimer: 
 mov x16, #(83) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getitimer 
 _getitimer: 
 mov x16, #(86) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getpriority 
 _getpriority: 
 mov x16, #(100) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setpriority 
 _setpriority: 
 mov x16, #(96) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getdtablesize 
 _getdtablesize: 
 mov x16, #(89) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getgroups 
 _getgroups: 
 mov x16, #(79) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _socket 
 _socket: 
 mov x16, #(97) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _connect 
 _connect: 
 mov x16, #(98) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _bind 
 _bind: 
 mov x16, #(104) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _setsockopt 
 _setsockopt: 
 mov x16, #(105) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getsockopt 
 _getsockopt: 
 mov x16, #(118) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _getpeername 
 _getpeername: 
 mov x16, #(31) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _sendto 
 _sendto: 
 mov x16, #(133) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _recvfrom 
 _recvfrom: 
 mov x16, #(29) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _recvmsg 
 _recvmsg: 
 mov x16, #(27) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _writev 
 _writev: 
 mov x16, #(121) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _pselect 
 _pselect: 
 mov x16, #(394) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.text 
 .align 2 
 .globl _shutdown 
 _shutdown: 
 mov x16, #(134) 
 svc #0x80 
 b.cc 2f 
 ARM64_STACK_PROLOG 
 stp fp, lr, [sp, #-16]! 
 mov fp, sp 
 
 bl _cerror_nocancel 
 mov sp, fp 
 ldp fp, lr, [sp], #16 
 
 ARM64_STACK_EPILOG 
2: 
 1: 
 ret
.subsections_via_symbols
