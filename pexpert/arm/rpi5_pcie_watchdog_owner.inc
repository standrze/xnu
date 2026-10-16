/* SPDX-License-Identifier: BSD-2-Clause */
/* Included ONLY by a separately patched pe_fiq.c; never by the accepted kernel. */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_PCI_WDOG_LEASE
#error "PCIe watchdog owner requires the opt-in BCM2712 DEVELOPMENT build"
#endif
#include <pexpert/arm/rpi5_pcie_watchdog_api.h>
#include "../../loader/rpi5/pcie_watchdog_gate.h"

static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;
static struct rpi5_pcie_watchdog_lease rpi5_pcie_wdog_lease;

static int
rpi5_pcie_wdog_route(void *context, uint32_t *out)
{
    (void)context;
    __builtin_arm_dsb(DSB_SY);
    *out = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC);
    __builtin_arm_dsb(DSB_SY);
    return 0; /* Abort/hang does NOT return an invented error. */
}
static int
rpi5_pcie_wdog_count(void *context, uint32_t *out)
{
    (void)context;
    __builtin_arm_dsb(DSB_SY);
    *out = rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_WDOG);
    __builtin_arm_dsb(DSB_SY);
    return 0;
}
static int
rpi5_pcie_wdog_write(void *context, uint32_t value)
{
    (void)context;
    rpi5_mmio_write32(rpi5_pm_base, RPI5_PM_WDOG, value);
    return 0;
}
static int
rpi5_pcie_wdog_order(void *context)
{
    (void)context;
    __builtin_arm_dsb(DSB_SY);
    return 0;
}
static int
rpi5_pcie_wdog_counter(void *context, uint64_t *out)
{
    (void)context;
    *out = __builtin_arm_rsr64("CNTVCT_EL0");
    return 0;
}

bool
pe_rpi5_watchdog_claim_pcie(const void *owner, struct rpi5_pcie_watchdog_observation *out)
{
    if (!owner || !out || ml_at_interrupt_context() || rpi5_pm_base == 0 ||
        !rpi5_pcie_watchdog_gate_claim(&rpi5_pcie_wdog_gate, owner)) return false;
    /* Linearized after any earlier service has completed, before physical
     * reads/write. All later timer/callout entries refuse the monotonic owner.
     * Even failure cannot resurrect a terminal/soak reload behind this lease. */
    bool available = rpi5_wdog_deadline != 0 && rpi5_wdog_soak_seconds == 0;
    /* Do not rewrite the legacy deadline: terminal_active reads it outside
     * this gate. The monotonic owner alone suppresses all servicing, even if
     * an already-queued callout reschedules itself before the hardware reset. */
    bool ok = false;
    if (available) {
        const struct rpi5_pcie_watchdog_io io = { NULL, rpi5_pcie_wdog_route, rpi5_pcie_wdog_count,
            rpi5_pcie_wdog_write, rpi5_pcie_wdog_order, rpi5_pcie_wdog_counter };
        uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
        ok = rpi5_pcie_watchdog_init(&rpi5_pcie_wdog_lease, &io, frequency) == 0 &&
            rpi5_pcie_watchdog_begin(&rpi5_pcie_wdog_lease, out) == 0;
    }
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_wdog_gate);
    return ok;
}

bool
pe_rpi5_watchdog_check_pcie(const void *owner)
{
    if (!owner || ml_at_interrupt_context() ||
        !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_wdog_gate, owner)) return false;
    bool ok = rpi5_pcie_watchdog_check(&rpi5_pcie_wdog_lease) == 0;
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_wdog_gate);
    return ok;
}

void
pe_rpi5_watchdog_timer_tick(bool healthy)
{
    if (!rpi5_pcie_watchdog_gate_service(&rpi5_pcie_wdog_gate)) return;
    rpi5_watchdog_service_unlocked(healthy);
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_wdog_gate);
}
