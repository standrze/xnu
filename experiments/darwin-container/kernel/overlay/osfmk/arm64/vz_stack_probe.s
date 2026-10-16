/* SPDX-License-Identifier: BSD-2-Clause
 * Copyright (c) 2026, XNU Raspberry Pi port contributors.
 * License text: tools/rpi5/LICENSE at the repository root.
 * VZGENERIC reuse of the portable Darwin stack-probe implementation,
 * downstream modification 2026-10-12: target guard/name only.
 *
 * x9 is the byte count; x16/x17 are scratch. Preserve SP, x9, other registers
 * and NZCV. Probe every 4 KiB and the endpoint so guard pages cannot be skipped.
 */
#if !defined(ARM64_BOARD_CONFIG_VZGENERIC) || !DEVELOPMENT
#error This runtime helper is restricted to VZGENERIC DEVELOPMENT
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
