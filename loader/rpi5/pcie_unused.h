/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_UNUSED_H
#define RPI5_PCIE_UNUSED_H
#include "pcie_ubus.h"

struct rpi5_pcie_unused_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*check_owner)(void *);
    int (*read32)(void *, uint32_t, uint32_t *);
};
enum rpi5_pcie_unused_state {
    RPI5_PCIE_UNUSED_EMPTY, RPI5_PCIE_UNUSED_READY, RPI5_PCIE_UNUSED_BUSY,
    RPI5_PCIE_UNUSED_COMPLETE, RPI5_PCIE_UNUSED_QUARANTINED
};
enum rpi5_pcie_unused_result {
    RPI5_PCIE_UNUSED_OK = 0, RPI5_PCIE_UNUSED_ARGUMENT = -1,
    RPI5_PCIE_UNUSED_STATE = -2, RPI5_PCIE_UNUSED_DEPENDENCY = -3,
    RPI5_PCIE_UNUSED_IO = -4, RPI5_PCIE_UNUSED_ACTIVE = -5,
    RPI5_PCIE_UNUSED_DRIFT = -6
};
struct rpi5_pcie_unused {
    struct rpi5_pcie_ubus *ubus;
    struct rpi5_pcie_unused_io io;
    enum rpi5_pcie_unused_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_unused_observation {
    uint32_t inbound_bar_lo[7], inbound_remap_lo[7]; /* Slots 4..10. */
    uint32_t outbound_base_limit[2], outbound_base_hi[2], outbound_limit_hi[2]; /* 2..3. */
    uint32_t final_status, final_control, final_debug;
    uint32_t remap_enabled_mask, completed_callbacks;
};

/* Real read-only prerequisite for the existing window programmer. The same
 * completed UBUS/SerDes/reset/calibration owner and mapping are required.
 * Zero-initialized, stable disjoint storage; output atomic. No MMIO at init.
 * check_owner is an independently bounded ownership/watchdog callback, NOT an
 * assertion that interrupts/endpoints/DMA are quiescent. Those and accessible
 * Device/power/clocks/shared lifecycle/recovery remain caller prerequisites. */
int rpi5_pcie_unused_init(struct rpi5_pcie_unused *, struct rpi5_pcie_ubus *,
    const struct rpi5_pcie_unused_io *);

/* Two 23-register snapshots with owner checks before/after every read and a
 * final publication guard: at most 139 callbacks. Require RC/link-down/PERST#
 * asserted/no L23 request/IDDQ released. Slots 4..10 must have BAR SIZE=0;
 * UBUS remap ACCESS_EN is recorded, not mistaken for a BAR enable. Outbound
 * slots 2..3 must have decoded inclusive base > limit, including high bytes.
 * Reject all-ones reads and changes to any window tuple between snapshots.
 * No writes, cleanup, retry, polls, delay, new watchdog claim or mapping.
 * COMPLETE is a momentary disabled-window observation, not interrupt/DMA/
 * power/recovery admission or permission to reuse it later without rechecking.
 * Failure quarantines this session plus UBUS/SerDes/MDIO, output unchanged.
 * Hung MMIO/abort containment is not established by a finite callback bound. */
int rpi5_pcie_unused_inspect(struct rpi5_pcie_unused *,
    struct rpi5_pcie_unused_observation *);
#endif
