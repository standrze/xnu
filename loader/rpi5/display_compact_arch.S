/* SPDX-License-Identifier: BSD-2-Clause */
/* Exactly one aligned32-bit store, no read/cache/mapping operation. Caller
 * validates address, ownership and MMU/cache-off state before every store. */
.text
.p2align 2
.global rpi5_display_compact_store
.type rpi5_display_compact_store,%function
rpi5_display_compact_store:
    str w1,[x0]
    ret
.size rpi5_display_compact_store,.-rpi5_display_compact_store
.global rpi5_display_compact_barrier
.type rpi5_display_compact_barrier,%function
rpi5_display_compact_barrier:
    dsb sy
    ret
.size rpi5_display_compact_barrier,.-rpi5_display_compact_barrier

