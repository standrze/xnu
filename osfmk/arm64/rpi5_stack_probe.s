/* SPDX-License-Identifier: BSD-2-Clause
 * Copyright (c) 2026, XNU Raspberry Pi port contributors.
 * License text: tools/rpi5/LICENSE at the repository root.
 * Raspberry Pi XNU downstream, 2026-09-04.
 *
 * Darwin stack-probe ABI verified with the installed compiler's
 * StkChkIndirectCall/csr_aarch64_stackprobe_darwin MIR: x9 is a byte count;
 * x16 and x17 are scratch. Preserve SP, x9, all other registers and NZCV.
 *
 * Probe downward at 4 KiB intervals, then at the requested endpoint. This
 * cannot skip a 16 KiB Pi guard page and also supports a 4 KiB host harness.
 * No stack memory is written and no exception is caught here: an inaccessible
 * stack page must fault before the caller moves SP past it.
 */

#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT
#error This runtime helper is restricted to BCM2712 DEVELOPMENT
#endif

	.text
	.p2align 2
	.globl ___chkstk_darwin
___chkstk_darwin:
	cbz x9, 3f
	lsr x16, x9, #12
	mov x17, sp
	cbz x16, 2f
1:
	sub x17, x17, #1, lsl #12
	ldr xzr, [x17]
	sub x16, x16, #1
	cbnz x16, 1b
2:
	sub x17, sp, x9
	ldrb wzr, [x17]
3:
	ret
