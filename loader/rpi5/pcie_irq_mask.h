/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_IRQ_MASK_H
#define RPI5_PCIE_IRQ_MASK_H
#include "pcie_fdt.h"

#define RPI5_PCIE_IRQ_BANKS 3u
enum rpi5_pcie_irq_state {
    RPI5_PCIE_IRQ_EMPTY, RPI5_PCIE_IRQ_READY, RPI5_PCIE_IRQ_BUSY,
    RPI5_PCIE_IRQ_MASKED, RPI5_PCIE_IRQ_QUARANTINED
};
struct rpi5_pcie_irq_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*check_owner)(void *);
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    int (*order)(void *);
};
struct rpi5_pcie_irq_mask {
    struct rpi5_pcie_irq_io io;
    enum rpi5_pcie_irq_state state;
    uint32_t callbacks;
};
struct rpi5_pcie_irq_observation {
    uint32_t typer, callbacks;
    uint32_t enabled_before[3], pending_before[3], active_before[3];
    uint32_t enabled[2][3], pending[2][3], active[2][3];
};

/* Fixed PCIe2/MIP0 routing only: INTIDs160..223 and261..266. Validate a real
 * original-FDT decoder result; copying field values is not firmware admission.
 * Zeroed stable storage; disjoint output. Init does no I/O. Caller independently
 * owns the retained GIC Device mapping, shared controller/power/clock lifecycle,
 * endpoint/DMA state, secure-firmware cooperation and bounded fault recovery.
 * check_owner is bounded nonreentrant ownership, NOT those physical proofs. */
int rpi5_pcie_irq_init(struct rpi5_pcie_irq_mask *, const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_irq_io *);

/* Caller must have armed the one-shot watchdog and masked local IRQ/FIQ before
 * begin. At most three exact ICENABLER W1C writes (banks5/6 all bits, bank8
 * 0x7e0); no read-modify-write, bank0/7 or NVMe bit writes, enable, pending/
 * active clear, group, priority, target, GICC acknowledge/EOI, poll or retry.
 * Refuse active selected interrupts before writes; after masking require two
 * samples with selected enable/active bits clear. Pending remains recorded,
 * including changes; MASKED is NOT source/endpoint/DMA quiescence. */
int rpi5_pcie_irq_begin(struct rpi5_pcie_irq_mask *, struct rpi5_pcie_irq_observation *);

/* Fresh read-only two-snapshot check. May be repeated only while MASKED and
 * the diagnostic watchdog lease holds. Neither operation releases ownership,
 * restores enables or cleans up on failure. Outputs publish only on success.
 * Non-secure RAZ/WI bits cannot establish secure ownership or implementation.
 * Finite callback bounds do not bound a CPU abort/hung register/barrier. */
int rpi5_pcie_irq_check(struct rpi5_pcie_irq_mask *, struct rpi5_pcie_irq_observation *);
#endif
