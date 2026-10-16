/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_RESET_H
#define RPI5_PCIE_RESET_H

#include "pcie_fdt.h"

/* PCIe2 bridge reset 44 only. Offsets below are relative to the FDT's
 * brcm,brcmstb-reset resource, NOT the PCIe bridge or RESCAL resource.
 * The provider must own an accessible Device mapping and serialize the whole
 * reset lifecycle. No callback may reenter. Return zero on success; each
 * callback must complete within a provider-enforced bound (including faults).
 * Numeric values are aligned little-endian MMIO values. A completion barrier
 * must precede status observation; delay_us must wait AT LEAST its argument.
 * No generic write callback is exposed: only one-bit SET/CLEAR writes exist. */
struct rpi5_pcie_reset_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*status)(void *, uint32_t *);
    int (*assert_bridge)(void *);   /* write 0x1000 at offset 0x18 */
    int (*deassert_bridge)(void *); /* write 0x1000 at offset 0x1c */
    int (*order)(void *);
    int (*delay_us)(void *, uint32_t);
};

enum rpi5_pcie_reset_state {
    RPI5_PCIE_RESET_EMPTY, RPI5_PCIE_RESET_READY,
    RPI5_PCIE_RESET_BUSY, RPI5_PCIE_RESET_COMPLETE,
    RPI5_PCIE_RESET_QUARANTINED
};
enum rpi5_pcie_reset_result {
    RPI5_PCIE_RESET_OK = 0, RPI5_PCIE_RESET_ARGUMENT = -1,
    RPI5_PCIE_RESET_STATE = -2, RPI5_PCIE_RESET_IO = -3,
    RPI5_PCIE_RESET_READBACK = -4
};
struct rpi5_pcie_reset {
    struct rpi5_pcie_reset_io io;
    enum rpi5_pcie_reset_state state;
    uint32_t completed_callbacks; /* diagnostic, not recovery authority */
};
struct rpi5_pcie_reset_observation {
    uint32_t before, asserted, released; /* complete bank status words */
};

/* Pure init, no I/O. Caller zero-initializes a new, disjoint session and passes
 * the validated runtime topology. Exact resource/ID checks do not establish
 * accessibility, power, clock or ownership. Init cannot recycle a used session. */
int rpi5_pcie_reset_init(struct rpi5_pcie_reset *,
    const struct rpi5_pcie_fdt *, const struct rpi5_pcie_reset_io *);

/* One bounded initial bridge reset pulse, not a runtime reset/recovery API.
 * Before calling, provider independently quiesces RP1/config/DMA, owns PCIe2
 * and the reset mapping, and closes shared RESCAL/power/clock dependencies.
 * No PCIe register is accessed here. The two 100-us waits cover assertion
 * hold and reset release settling; status bit 12 must confirm each phase.
 * Other bank bits are observed but never written, compared or restored.
 *
 * Any callback/readback failure quarantines the session, stops immediately,
 * leaves out unchanged, and does NOT undo a possibly completed hardware write.
 * No retry, cleanup reset, RESCAL trigger or other controller reset occurs.
 * Success proves this pulse only, NOT bridge register accessibility, SerDes
 * stabilization, link training, window programming or NIC readiness.
 * This core is not wired into BL33/XNU until the provider contract is closed. */
int rpi5_pcie_reset_pulse(struct rpi5_pcie_reset *,
    struct rpi5_pcie_reset_observation *out);

#endif
