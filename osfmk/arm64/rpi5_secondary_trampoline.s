/* SPDX-License-Identifier: BSD-2-Clause
 * Copyright (c) 2026, XNU Raspberry Pi port contributors.
 * License text: tools/rpi5/LICENSE at the repository root.
 *
 * PSCI CPU_ON64 physical entry for BCM2712 secondaries. The caller passes the
 * physical address of XNU's LowResetVectorBase page as context_id.
 * That page and its ResetHandlerData/CpuDataEntries must be published to the
 * point of coherency before CPU_ON. This code makes no memory references and
 * needs no stack or virtual mapping before entering the existing reset path.
 */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT
#error This trampoline is restricted to BCM2712 DEVELOPMENT
#endif

	.text
	.p2align 11
	.globl _rpi5_secondary_trampoline
_rpi5_secondary_trampoline:
	msr daifset, #15
	mrs x9, CurrentEL
	cmp x9, #8			/* PSCI firmware must enter in EL2. */
	b.ne Lrpi5_secondary_park
	cbz x0, Lrpi5_secondary_park
	tst x0, #0xfff			/* Reset vector is page aligned. */
	b.ne Lrpi5_secondary_park
	mrs x9, sctlr_el2
	mov x10, #0x1005		/* Require EL2 M, C and I clear. */
	tst x9, x10
	b.ne Lrpi5_secondary_park

	/* Any early EL2 exception parks without dereferencing a virtual address. */
	adr x9, Lrpi5_secondary_vectors
	msr vbar_el2, x9
	isb

	/* A76, non-VHE, EL1 AArch64, stage 2 disabled, IRQs routed to EL1. */
	mov x9, #0x80000000
	msr hcr_el2, x9
	isb
	mov x9, #3
	msr cnthctl_el2, x9
	msr cntvoff_el2, xzr
	mov x9, #0x33ff		/* CPTR_EL2 RES1, no FP trap. */
	msr cptr_el2, x9
	msr mdcr_el2, xzr
	msr hstr_el2, xzr
	msr vttbr_el2, xzr
	mov x9, #0x0800
	movk x9, #0x30d0, lsl #16	/* SCTLR_EL1 RES1, M/C/I off. */
	msr sctlr_el1, x9
	msr cpacr_el1, xzr
	msr cntkctl_el1, xzr
	msr cntv_ctl_el0, xzr
	msr cntp_ctl_el0, xzr
	msr sp_el1, xzr
	msr elr_el2, x0
	mov x9, #0x3c5		/* DAIF masked, EL1h. */
	msr spsr_el2, x9
	dsb sy
	isb
	eret

Lrpi5_secondary_park:
	wfe
	b Lrpi5_secondary_park

	/* EL2 vector slots must each occupy 128 bytes. */
	.p2align 11
Lrpi5_secondary_vectors:
	.rept 16
	b Lrpi5_secondary_park
	.balign 128
	.endr
	.globl _rpi5_secondary_trampoline_end
_rpi5_secondary_trampoline_end:
