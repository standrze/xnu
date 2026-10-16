/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual faultable early accesses. No exception fixups, no error return and no
 * pointer discovery. Caller admits exactly the read-only register list while
 * EL1 stage1/stage2/MMU/cache are disabled and an autonomous watchdog is armed.
 * The barriers can also fault/hang; the watchdog is the intended whole-image
 * recovery mechanism, NOT an architectural guarantee of bounded completion. */
.text
.global rpi5_access_load32
.type rpi5_access_load32,%function
rpi5_access_load32:
    dsb sy
    ldr w0, [x0]
    dsb sy
    ret
.size rpi5_access_load32, .-rpi5_access_load32
.global rpi5_access_load16
.type rpi5_access_load16,%function
rpi5_access_load16:
    dsb sy
    ldrh w0, [x0]
    dsb sy
    ret
.size rpi5_access_load16, .-rpi5_access_load16

/* Unexpected masked IRQ: do not return into an interrupted read. */
.global probe_irq_entry
.type probe_irq_entry,%function
probe_irq_entry:
    msr daifset, #15
1:  wfe
    b 1b
.size probe_irq_entry, .-probe_irq_entry
