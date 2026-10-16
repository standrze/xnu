/* SPDX-License-Identifier: BSD-2-Clause */
/* The actual C protocol restricts offsets to the selective GIC allowlist. */
#if !RPI5_PCIE_FW_TRIAL
#error "Separate firmware ABI trial only"
#endif
.text
.global rpi5_fw_trial_daif
.type rpi5_fw_trial_daif,%function
rpi5_fw_trial_daif:
    mrs x0, daif
    ret
.size rpi5_fw_trial_daif, .-rpi5_fw_trial_daif
.global rpi5_fw_trial_affinity
.type rpi5_fw_trial_affinity,%function
rpi5_fw_trial_affinity:
    mrs x0, mpidr_el1
    movz x9, #0xffff
    movk x9, #0xff, lsl #16
    movk x9, #0xff, lsl #32
    and x0, x0, x9
    ret
.size rpi5_fw_trial_affinity, .-rpi5_fw_trial_affinity
.global rpi5_fw_trial_gic_load
.type rpi5_fw_trial_gic_load,%function
rpi5_fw_trial_gic_load:
    movz x9, #0x9000
    movk x9, #0x7fff, lsl #16
    movk x9, #0x10, lsl #32
    add x9, x9, w0, uxtw
    dsb sy
    ldr w0, [x9]
    dsb sy
    ret
.size rpi5_fw_trial_gic_load, .-rpi5_fw_trial_gic_load
.global rpi5_fw_trial_gic_store
.type rpi5_fw_trial_gic_store,%function
rpi5_fw_trial_gic_store:
    movz x9, #0x9000
    movk x9, #0x7fff, lsl #16
    movk x9, #0x10, lsl #32
    add x9, x9, w0, uxtw
    dsb sy
    str w1, [x9]
    dsb sy
    ret
.size rpi5_fw_trial_gic_store, .-rpi5_fw_trial_gic_store
