/* SPDX-License-Identifier: BSD-2-Clause */
	.text
	.p2align 2
	.globl _rpi5_test_probe
_rpi5_test_probe:
	stp x29, x30, [sp, #-16]!
	mov x29, sp
	mov x9, x1
	mov x10, #0x1234
	mov x11, #0x5678
	mov x16, #0xa0000000
	msr NZCV, x16
	mov sp, x0
	bl ___chkstk_darwin
	mrs x17, NZCV
	mov x16, sp
	mov sp, x29
	cmp x16, x0
	b.ne 1f
	mov x16, #0xa0000000
	cmp x17, x16
	b.ne 1f
	cmp x9, x1
	b.ne 1f
	mov x16, #0x1234
	cmp x10, x16
	b.ne 1f
	mov x16, #0x5678
	cmp x11, x16
	b.ne 1f
	mov w0, #0
	b 2f
1:
	mov w0, #1
2:
	ldp x29, x30, [sp], #16
	ret
