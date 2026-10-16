.align 2 
 .globl __setjmp 
 .text 
__setjmp:
 mov x12, sp
 mrs x16, TPIDRRO_EL0 
 ldr x16, [ x16, #((64/8)*7) ]
 eor x10, fp, x16
 eor x11, lr, x16
 eor x12, x12, x16
 stp x19, x20, [x0, #0x00]
 stp x21, x22, [x0, #0x10]
 stp x23, x24, [x0, #0x20]
 stp x25, x26, [x0, #0x30]
 stp x27, x28, [x0, #0x40]
 stp x10, x11, [x0, #0x50]
 str x12, [x0, #0x60]
 stp d8, d9, [x0, #0x70]
 stp d10, d11, [x0, #0x80]
 stp d12, d13, [x0, #0x90]
 stp d14, d15, [x0, #0xA0]
 mov w0, #0
 ret
.align 2 
 .globl __longjmp 
 .text 
__longjmp:
 ldp x19, x20, [x0, #0x00]
 ldp x21, x22, [x0, #0x10]
 ldp x23, x24, [x0, #0x20]
 ldp x25, x26, [x0, #0x30]
 ldp x27, x28, [x0, #0x40]
 ldp x10, x11, [x0, #0x50]
 ldr x12, [x0, #0x60]
 ldp d8, d9, [x0, #0x70]
 ldp d10, d11, [x0, #0x80]
 ldp d12, d13, [x0, #0x90]
 ldp d14, d15, [x0, #0xA0]
 mrs x16, TPIDRRO_EL0 
 ldr x16, [ x16, #((64/8)*7) ]
 eor fp, x10, x16
 eor lr, x11, x16
 eor x12, x12, x16
 ldrb w16, [sp]
 mov sp, x12
 cmp w1, #0
 csinc w0, w1, wzr, ne
 ret
.macro FUNC_PROLOGUE
.endmacro
.macro FUNC_EPILOGUE_TAILCALL f
 b \f
.endmacro
.align 2 
 .globl _sigsetjmp 
 .text 
_sigsetjmp:
 str w1, [x0, #0xB8]
 cbnz w1, 1f
 b __setjmp
1:
.align 2 
 .globl _setjmp 
 .text 
_setjmp:
 FUNC_PROLOGUE
 stp x21, lr, [x0]
 mov x21, x0
 orr w0, wzr, #0x1
 mov x1, #0
 add x2, x21, #0xB0
 bl _sigprocmask
 sub sp, sp, #32
 mov x0, xzr
 mov x1, sp
 bl ___sigaltstack
 ldr w0, [sp, 16]
 str w0, [x21, #0xBC]
 add sp, sp, #32
 mov x0, x21
 ldp x21, lr, [x0]
 FUNC_EPILOGUE_TAILCALL __setjmp
.align 2 
 .globl _siglongjmp 
 .text 
_siglongjmp:
 ldr w8, [x0, #0xB8]
 cbnz w8, 1f
 b __longjmp
1:
.align 2 
 .globl _longjmp 
 .text 
_longjmp:
 sub sp, sp, #16
 mov x21, x0
 mov x22, x1
 ldr x8, [x21, #0xB0]
 str x8, [sp, #8]
 orr w0, wzr, #0x3
 add x1, sp, #8
 mov x2, #0
 bl _sigprocmask
 ldr x0, [x21, #0xBC]
 bl __sigunaltstack
 mov x0, x21
 mov x1, x22
 add sp, sp, #16
 b __longjmp
