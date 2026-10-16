/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_WINDOWS_H
#define RPI5_PCIE_WINDOWS_H

#include "pcie_fdt.h"

enum rpi5_pcie_window_padding {
    RPI5_PCIE_WINDOW_EXACT = 0,
    /* Only the known PCIe2 MEM32 [0,0xfffffffc) declaration may round by 4.
     * This acknowledges a hardware decode excess, NOT permission to use it. */
    RPI5_PCIE_WINDOW_ACK_FOUR_BYTES = 1
};
struct rpi5_pcie_outbound_encoding {
    uint64_t cpu_base, declared_end, decode_end, pci_base, size;
    uint32_t pci_lo, pci_hi, base_limit, base_hi, limit_hi, padding_bytes;
};
struct rpi5_pcie_inbound_encoding {
    uint64_t cpu_base, pci_base, size;
    uint32_t bar_lo, bar_hi, remap_lo, remap_hi;
};
struct rpi5_pcie_window_plan {
    struct rpi5_pcie_outbound_encoding outbound[2];
    struct rpi5_pcie_inbound_encoding inbound[3];
};

/* Pure encoding of the decoded PCIe2 binding, not live translation evidence.
 * Validates both directions separately: 40-bit spans, MEM32 limits, alignment,
 * address-space flags and hardware-decode overlaps (including mixed flags).
 * Inbound sizes must be powers of two from 4 KiB through 64 GiB. The 64-GiB
 * RAM reachability window does NOT describe installed RAM or allocate DMA.
 * Outbound bases must be 1-MiB aligned; arbitrary rounding is rejected.
 * Inputs/output must be stable and disjoint; output unchanged on failure. */
int rpi5_pcie_windows_plan(const struct rpi5_pcie_fdt *,
    enum rpi5_pcie_window_padding, struct rpi5_pcie_window_plan *out);

/* Provider owns the exact accessible Device mapping, completed initial reset,
 * power/clocks/shared calibration and exclusive controller lifecycle. It must
 * bound/contain every callback and keep all inputs/session objects stable.
 * check_quiescent must verify ownership, endpoints and DMA quiesced, and all
 * unused inbound slots 4..10/outbound slots 2..3 independently disabled/safe.
 * Those unused slots are NOT modified or audited here. A zero return is a
 * provider obligation, not software proof of any of these physical conditions.
 * This core additionally reads RC role, link-down and asserted PERST# before
 * each window and publication. No callback may reenter or release ownership. */
struct rpi5_pcie_windows_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*check_quiescent)(void *);
    int (*read32)(void *, uint32_t offset, uint32_t *);
    int (*write32)(void *, uint32_t offset, uint32_t);
    int (*order)(void *);
};
enum rpi5_pcie_windows_state {
    RPI5_PCIE_WINDOWS_EMPTY, RPI5_PCIE_WINDOWS_READY, RPI5_PCIE_WINDOWS_BUSY,
    RPI5_PCIE_WINDOWS_COMPLETE, RPI5_PCIE_WINDOWS_QUARANTINED
};
enum rpi5_pcie_windows_result {
    RPI5_PCIE_WINDOWS_OK = 0, RPI5_PCIE_WINDOWS_ARGUMENT = -1,
    RPI5_PCIE_WINDOWS_STATE = -2, RPI5_PCIE_WINDOWS_IO = -3,
    RPI5_PCIE_WINDOWS_READBACK = -4, RPI5_PCIE_WINDOWS_NOT_QUIESCENT = -5
};
struct rpi5_pcie_windows {
    struct rpi5_pcie_windows_io io;
    struct rpi5_pcie_window_plan plan;
    enum rpi5_pcie_windows_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_windows_observation {
    uint32_t inbound_programmed, outbound_programmed, padding_bytes;
    uint32_t final_status, final_control, completed_callbacks;
};

/* Pure init for zero-initialized disjoint storage. Takes a private plan copy;
 * caller may subsequently discard FDT/io inputs, but not mutate the session.
 * No MMIO or ownership claim happens at init. No boot/kernel caller exists. */
int rpi5_pcie_windows_init(struct rpi5_pcie_windows *, const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_windows_io *, enum rpi5_pcie_window_padding);

/* One-shot programming of inbound slots 1..3 and outbound slots 0..1, with
 * ordered writes, target-field readbacks and an independent final full pass.
 * <=112 callbacks, no polls. Finite core != bounded/fault-safe actual MMIO.
 * Failure quarantines without further callbacks, cleanup, retry or rollback;
 * writes may already have taken effect. Output unchanged on failure.
 * COMPLETE is only this subset, not controller admission, PERST release/link,
 * endpoint BAR assignment, RAM ownership, IRQ/MSI, bus mastering or DMA enable.
 * This component is deliberately absent from all actual build source lists. */
int rpi5_pcie_windows_program(struct rpi5_pcie_windows *,
    struct rpi5_pcie_windows_observation *out);

#endif
