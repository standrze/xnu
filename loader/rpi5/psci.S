/* SPDX-License-Identifier: BSD-2-Clause
 * PSCI SMC32/SMC64 read-only query. x0=fid, x1=query; x2/x3 cleared.
 * AFFINITY_INFO64 therefore queries lowest_affinity_level=0.
 * TF-A/SMCCC must preserve the AAPCS64 callee-saved registers.
 */
.text
.global rpi5_psci_query
.type rpi5_psci_query,%function
rpi5_psci_query:
    mov x2, xzr
    mov x3, xzr
    smc #0
    ret
.size rpi5_psci_query, .-rpi5_psci_query

/* CPU_ON64: x0=target affinity, x1=entry PA, x2=context slot. */
.global rpi5_psci_cpu_on
.type rpi5_psci_cpu_on,%function
rpi5_psci_cpu_on:
    mov x3, x2
    mov x2, x1
    mov x1, x0
    mov x0, #3
    movk x0, #0xc400, lsl #16
    smc #0
    ret
.size rpi5_psci_cpu_on, .-rpi5_psci_cpu_on

/* CPU_OFF32 never returns on success. On error, park without retrying. */
.global rpi5_psci_cpu_off
.type rpi5_psci_cpu_off,%function
rpi5_psci_cpu_off:
    msr daifset, #0xf
    dsb sy
    mov x0, #2
    movk x0, #0x8400, lsl #16
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    smc #0
1:  wfe
    b 1b
.size rpi5_psci_cpu_off, .-rpi5_psci_cpu_off
