/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_ACCESS_H
#define RPI5_PCIE_ACCESS_H

#include "pcie_fdt.h"

#define RPI5_PCIE_ACCESS_REGISTERS 15
struct rpi5_pcie_access_register {
    uint64_t address;
    uint32_t width;
};
struct rpi5_pcie_access_io {
    void *context;
    int (*arm_guard)(void *); /* Require/reload an already-armed full-reset WD. */
    int (*check_guard)(void *); /* Check routing/countdown; NEVER reload. */
    int (*now_us)(void *, uint64_t *);
    int (*before_read)(void *, unsigned pass, unsigned index, uint64_t address, unsigned width);
    int (*read)(void *, uint64_t address, unsigned width, uint32_t *);
    int (*after_read)(void *, unsigned pass, unsigned index, uint32_t value);
};
enum rpi5_pcie_access_state {
    RPI5_PCIE_ACCESS_EMPTY, RPI5_PCIE_ACCESS_READY, RPI5_PCIE_ACCESS_BUSY,
    RPI5_PCIE_ACCESS_COMPLETE, RPI5_PCIE_ACCESS_QUARANTINED
};
enum rpi5_pcie_access_result {
    RPI5_PCIE_ACCESS_OK = 0, RPI5_PCIE_ACCESS_ARGUMENT = -1,
    RPI5_PCIE_ACCESS_STATE = -2, RPI5_PCIE_ACCESS_IO = -3,
    RPI5_PCIE_ACCESS_VALUE = -4, RPI5_PCIE_ACCESS_CLOCK = -5,
    RPI5_PCIE_ACCESS_TIMEOUT = -6
};
struct rpi5_pcie_access {
    struct rpi5_pcie_access_io io;
    struct rpi5_pcie_access_register registers[RPI5_PCIE_ACCESS_REGISTERS];
    enum rpi5_pcie_access_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_access_observation {
    uint32_t values[2][RPI5_PCIE_ACCESS_REGISTERS];
    uint64_t elapsed_us;
};

/* Pure init, exact translated resources and stable/disjoint zeroed objects.
 * No PCIe configuration/reset/calibration writes, config selector, RP1, IRQ,
 * bus mastering or DMA. List contains only named non-clear-on-read registers.
 * Software init does not establish accessibility or power/clock ownership. */
int rpi5_pcie_access_init(struct rpi5_pcie_access *, const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_access_io *);

/* Arm -> two ordered 15-register read-only passes with guard and before/after
 * logging -> final guard. <=184 callbacks, measured <=5 s including returned
 * callbacks. No retry/cleanup/rollback. Output unchanged on failure, partial
 * logs remain evidence only. All-ones, invalid halfwords and nonadvancing/
 * regressing/wrapped clocks reject. Dynamic register differences are reported,
 * not treated as stability, link or NIC admission. Used sessions cannot rearm.
 * Real loads may abort/hang rather than return IO errors. The distinct early
 * image deliberately uses fatal vectors and an autonomous watchdog, not a
 * resumable/no-fault MMIO API. Reset and safe boot destination must be proven
 * separately before admitting it as a recovery-contained hardware provider. */
int rpi5_pcie_access_capture(struct rpi5_pcie_access *,
    struct rpi5_pcie_access_observation *);

#endif
