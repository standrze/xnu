
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
 .align 2
 .globl __thread_set_tsd_base
__thread_set_tsd_base:
 mov x3, #2
 mov x16, #0x80000000
 svc #0x80
 ret
.subsections_via_symbols
