/* SPDX-License-Identifier: BSD-2-Clause */
.text
.global rpi5_fw_load32
.type rpi5_fw_load32,%function
rpi5_fw_load32:
    dsb sy
    ldr w0, [x0]
    dsb sy
    ret
.size rpi5_fw_load32, .-rpi5_fw_load32
.global rpi5_fw_counter
.type rpi5_fw_counter,%function
rpi5_fw_counter:
    isb
    mrs x0, cntpct_el0
    ret
.size rpi5_fw_counter, .-rpi5_fw_counter
.global rpi5_fw_frequency
.type rpi5_fw_frequency,%function
rpi5_fw_frequency:
    mrs x0, cntfrq_el0
    ret
.size rpi5_fw_frequency, .-rpi5_fw_frequency
.global rpi5_fw_trylock
.type rpi5_fw_trylock,%function
rpi5_fw_trylock:
    ldaxr w1, [x0]
    cbnz w1, 1f
    mov w1, #1
    stxr w2, w1, [x0]
    cbnz w2, 1f
    mov w0, #1
    ret
1:  clrex
    mov w0, #0
    ret
.size rpi5_fw_trylock, .-rpi5_fw_trylock
.global rpi5_fw_unlock
.type rpi5_fw_unlock,%function
rpi5_fw_unlock:
    stlr wzr, [x0]
    ret
.size rpi5_fw_unlock, .-rpi5_fw_unlock
