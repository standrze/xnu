/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_FW_CLIENT
#error "Private PCIe SMCCC requires its separate diagnostic build"
#endif
#ifdef __APPLE__
#define SYMBOL(name) _##name
#else
#define SYMBOL(name) name
#endif
.text
.p2align 2
.global SYMBOL(rpi5_pcie_fw_smccc)
#ifndef __APPLE__
.type rpi5_pcie_fw_smccc,%function
#endif
SYMBOL(rpi5_pcie_fw_smccc):
    stp x29, x30, [sp, #-32]!
    mov x29, sp
    stp x19, x20, [sp, #16]
    mov x19, x2
    mov x2, xzr
    mov x3, xzr
    mov x4, xzr
    mov x5, xzr
    mov x6, xzr
    mov x7, xzr
    dsb sy
    smc #0
    isb
    stp x0, x1, [x19]
    stp x2, x3, [x19, #16]
    ldp x19, x20, [sp, #16]
    ldp x29, x30, [sp], #32
    ret
#ifndef __APPLE__
.size rpi5_pcie_fw_smccc, .-rpi5_pcie_fw_smccc
#endif
