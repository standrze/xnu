
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
.private_extern ___gettimeofday_with_mach
.text 
 .align 2 
 .globl ___gettimeofday_with_mach 
 ___gettimeofday_with_mach: 
 mov x16, #(116) 
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
.globl ___gettimeofday
___gettimeofday:
    movz x2, #0x0
    mov x16, #(116) 
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
