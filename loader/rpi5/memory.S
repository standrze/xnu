/* SPDX-License-Identifier: BSD-2-Clause
 * AAPCS64 memcpy: ordinary readable/writable, non-overlapping ranges.
 * Byte accesses support arbitrary alignment; returns original destination.
 */
.text
.global memcpy
.type memcpy,%function
memcpy:
    mov x3, x0
    cbz x2, 2f
1:  ldrb w4, [x1], #1
    strb w4, [x3], #1
    subs x2, x2, #1
    b.ne 1b
2:  ret
.size memcpy, .-memcpy

/* AAPCS64 memset: low byte of w1, x2 bytes, original destination returned. */
.global memset
.type memset,%function
memset:
    mov x3, x0
    cbz x2, 2f
1:  strb w1, [x3], #1
    subs x2, x2, #1
    b.ne 1b
2:  ret
.size memset, .-memset
