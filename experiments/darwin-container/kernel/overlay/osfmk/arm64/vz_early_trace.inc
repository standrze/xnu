/* SPDX-License-Identifier: BSD-2-Clause
 * VZ-only diagnostic transport for the loader-established split TX queue.
 * Entry extension: x2 is the retained physical shared-console record; x0
 * remains the standard boot_args pointer. No stack, allocation or reset.
 * These checkpoints are not boot-success evidence. Remove after bring-up.
 */
#if defined(ARM64_BOARD_CONFIG_VZGENERIC)

/* x27 = shared record PA, w16 = byte. Clobbers x9-x15 and NZCV only.
 * Bounded polling avoids turning a stopped host consumer into a guest hang.
 * The shared-record offsets match loader/vz/virtio_console.h. Only call with
 * translation disabled or while the temporary identity mappings remain.
 */
.macro vz_early_tx
	cbz x27, 989f
	ldr x9, [x27, #32]
	mov x15, #0x100000
980:
	dmb oshld
	ldrh w10, [x9, #0x102]
	ldrh w11, [x9, #0x202]
	cmp w10, w11
	b.eq 981f
	subs x15, x15, #1
	b.ne 980b
	b 989f
981:
	strb w16, [x9, #0x400]
	mov w11, #1
	str w11, [x9, #8]
	and x12, x10, #7
	add x13, x9, #0x104
	strh wzr, [x13, x12, lsl #1]
	dmb osh
	add w10, w10, #1
	strh w10, [x9, #0x102]
	ldr x11, [x27, #16]
	ldrh w12, [x27, #46]
	ldr w13, [x27, #40]
	umull x12, w12, w13
	add x11, x11, x12
	dmb osh
	mov w13, #1
	strh w13, [x11]
	dsb sy
989:
.endmacro

.macro vz_early_mark byte
	mov w16, #\byte
	vz_early_tx
.endmacro

/* Two discovered BAR pages in one otherwise unused L2 slot. The observed VZ
 * console has common/notify in the same 32-MiB region. Reject a different
 * layout rather than replacing any RAM mapping or widening Device coverage.
 * x25 is bootstrap TTBR0; clobbers x9-x16/NZCV after RAM tables are finished.
 */
.macro vz_early_map_io
	ldr x9, [x27, #8]
	ldr x10, [x27, #16]
	orr x11, x9, x10
	lsr x11, x11, #36
	cbnz x11, 988f
	eor x11, x9, x10
	lsr x11, x11, #25
	cbnz x11, 988f
	ldr x11, [x25]
	and x12, x11, #3
	cmp x12, #3
	b.ne 988f
	and x11, x11, #0x0000000fffffc000
	ubfx x12, x9, #25, #11
	add x11, x11, x12, lsl #3
	ldr x12, [x11]
	cbnz x12, 988f
	adrp x12, EXT(vz_early_io_table)@page
	add x12, x12, EXT(vz_early_io_table)@pageoff
	mov x13, x12
	mov x14, #2048
984:
	str xzr, [x13], #8
	subs x14, x14, #1
	b.ne 984b
	MOV64 x15, 0x006000000000060f
	and x13, x9, #0x0000000fffffc000
	orr x13, x13, x15
	ubfx x14, x9, #14, #11
	str x13, [x12, x14, lsl #3]
	and x13, x10, #0x0000000fffffc000
	orr x13, x13, x15
	ubfx x14, x10, #14, #11
	str x13, [x12, x14, lsl #3]
	dsb ishst
	orr x12, x12, #3
	str x12, [x11]
	dsb ish
	b 987f
988:
	vz_early_mark 81 // Q: unsupported/conflicting early MMIO mapping
986:
	wfe
	b 986b
987:
.endmacro

	.zerofill __DATA,__bss,EXT(vz_early_io_table),0x4000,14
	.data
	.align 3
	.globl EXT(vz_early_console_pa)
LEXT(vz_early_console_pa)
	.quad 0
	.text
	.align 2
	.globl EXT(vz_early_c_mark)
LEXT(vz_early_c_mark)
	/* C may use x27; save/restore its value without borrowing a stack. */
	mov x8, x27
	adrp x9, EXT(vz_early_console_pa)@page
	add x9, x9, EXT(vz_early_console_pa)@pageoff
	ldr x27, [x9]
	mov w16, w0
	vz_early_tx
	mov x27, x8
	ret

	.globl EXT(vz_early_trace_end)
LEXT(vz_early_trace_end)
	/* Called at KVA immediately before arm_vm_init removes TTBR0 maps. */
	adrp x9, EXT(ExceptionVectorsBase)@page
	add x9, x9, EXT(ExceptionVectorsBase)@pageoff
	msr VBAR_EL1, x9
	isb
	ret

/* Hex dumper preserves x19-x29 (diagnostic register snapshots). */
.macro vz_early_hex reg
	mov x17, \reg
	mov x18, #16
982:
	lsr x14, x17, #60
	cmp x14, #10
	add x16, x14, #48
	add x14, x14, #87
	csel x16, x16, x14, lo
	vz_early_tx
	lsl x17, x17, #4
	subs x18, x18, #1
	b.ne 982b
.endmacro

	.text
	.align 12, 0
L_vz_early_vectors:
	.rept 16
	b L_vz_early_exception
	.align 7, 0
	.endr
L_vz_early_exception:
	msr DAIFSet, #(DAIFSC_ALL)
	mrs x19, ESR_EL1
	mrs x20, ELR_EL1
	mrs x21, FAR_EL1
	adrp x9, EXT(vz_early_console_pa)@page
	add x9, x9, EXT(vz_early_console_pa)@pageoff
	ldr x27, [x9]
	vz_early_mark 10
	vz_early_mark 33
	vz_early_mark 69
	vz_early_hex x19
	vz_early_mark 32
	vz_early_mark 76
	vz_early_hex x20
	vz_early_mark 32
	vz_early_mark 70
	vz_early_hex x21
	vz_early_mark 10
983:
	wfe
	b 983b
#endif
