/* SPDX-License-Identifier: BSD-2-Clause */
/* MMU-off identity VA, page-isolated buffers, 64-byte Cortex-A76 lines.
 * Ordered PoC operations follow the pinned TF-A cache_helpers.S semantics.
 * Exactly one page per call; no unbounded caller-controlled loop. */
.text
.p2align 2
.global rpi5_display_query_identity
.type rpi5_display_query_identity,%function
rpi5_display_query_identity:
    ret
.size rpi5_display_query_identity,.-rpi5_display_query_identity
.global rpi5_display_query_registers
.type rpi5_display_query_registers,%function
rpi5_display_query_registers:
    mrs x1,CurrentEL
    mrs x2,sctlr_el1
    stp x1,x2,[x0]
    mrs x1,daif
    mrs x2,mpidr_el1
    stp x1,x2,[x0,#16]
    mrs x1,cntfrq_el0
    mrs x2,ctr_el0
    stp x1,x2,[x0,#32]
    mrs x1,midr_el1
    str x1,[x0,#48]
    ret
.size rpi5_display_query_registers,.-rpi5_display_query_registers
.global rpi5_display_query_counter
.type rpi5_display_query_counter,%function
rpi5_display_query_counter:
    isb
    mrs x0,cntvct_el0
    ret
.size rpi5_display_query_counter,.-rpi5_display_query_counter
.global rpi5_display_query_read
.type rpi5_display_query_read,%function
rpi5_display_query_read:
    dsb sy
    ldr w0,[x0]
    dsb sy
    ret
.size rpi5_display_query_read,.-rpi5_display_query_read
.global rpi5_display_query_write
.type rpi5_display_query_write,%function
rpi5_display_query_write:
    dsb sy
    str w1,[x0]
    dsb sy
    ret
.size rpi5_display_query_write,.-rpi5_display_query_write
.macro page_cache name,op
.global \name
.type \name,%function
\name:
    dsb sy
    mov x1,#64
1:  dc \op,x0
    add x0,x0,#64
    subs x1,x1,#1
    b.ne 1b
    dsb sy
    ret
.size \name,.-\name
.endm
page_cache rpi5_display_query_clean,cvac
page_cache rpi5_display_query_invalidate,ivac
