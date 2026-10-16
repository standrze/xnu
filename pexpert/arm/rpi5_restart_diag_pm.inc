/* SPDX-License-Identifier: BSD-2-Clause
 * Appended only to the exact separately derived accepted watchdog owner TU.
 * Hardware accesses are read-only through its already validated Device map.
 */
#include "pexpert/arm/rpi5_restart_diag_api.h"
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_PCI_WDOG_LEASE
#error "Restart snapshot requires the exact BCM2712 watchdog service owner"
#endif
int rpi5_restart_diag_snapshot(struct rpi5_restart_diag_snapshot *out)
{
    if (!out || rpi5_pm_base == 0 ||
        !rpi5_pcie_watchdog_gate_service(&rpi5_pcie_wdog_gate)) return -1;
    int rc = -1;
    struct rpi5_restart_diag_snapshot value = {0};
    value.cntfrq = __builtin_arm_rsr64("CNTFRQ_EL0");
    value.cntvct_before = __builtin_arm_rsr64("CNTVCT_EL0");
    value.terminal_deadline = rpi5_wdog_deadline;
    __builtin_arm_dsb(DSB_SY);
    uint32_t route0 = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC);
    uint32_t count0 = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_WDOG);
    uint32_t count1 = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_WDOG);
    uint32_t route1 = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC);
    __builtin_arm_dsb(DSB_SY);
    value.cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
    value.watchdog_count_before = count0 & UINT32_C(0xfffff);
    value.watchdog_remaining_ticks = count1 & UINT32_C(0xfffff);
    value.full_reset_route = 1; /* Validated enabled-route boolean, not raw RSTC. */
    value.watchdog_nominal_hz = UINT32_C(65536);
    /* Source encoding, NOT a measured frequency/guaranteed future rate. */
    value.watchdog_rate_bound_proven = 0;
    if (rpi5_wdog_terminal_enabled && value.terminal_deadline != 0 &&
        value.cntfrq >= 100 && value.cntfrq <= UINT32_MAX &&
        value.cntvct >= value.cntvct_before &&
        value.cntvct - value.cntvct_before < value.cntfrq / 100 &&
        value.cntvct < value.terminal_deadline &&
        route0 != UINT32_MAX && route0 == route1 && (route1 & 0x30U) == RPI5_PM_FULL_RESET &&
        count0 != UINT32_MAX && count1 != UINT32_MAX &&
        value.watchdog_count_before <= RPI5_WDOG_INTERVAL &&
        value.watchdog_remaining_ticks <= value.watchdog_count_before &&
        value.watchdog_remaining_ticks > (2U << 16)) {
        *out = value;
        rc = 0;
    }
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_wdog_gate);
    return rc;
}
