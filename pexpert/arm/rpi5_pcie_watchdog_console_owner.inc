/* SPDX-License-Identifier: BSD-2-Clause */
/* Console extension for the existing short PCIe owner. Its distinct gate does
 * not suppress the independently bounded terminal-watchdog service. */
#include <pexpert/arm/rpi5_pcie_watchdog_owner.inc>
#include <pexpert/arm/rpi5_pcie_watchdog_console_api.h>

static struct rpi5_pcie_watchdog_gate rpi5_usb_console_wdog_gate;
static struct rpi5_pcie_watchdog_console_lease rpi5_usb_console_wdog_lease;

static int
rpi5_usb_console_wdog_active(void *context)
{
    (void)context;
    return pe_rpi5_watchdog_terminal_active() ? 1 : 0;
}

bool
pe_rpi5_watchdog_claim_usb_console(const void *owner,
    struct rpi5_pcie_watchdog_console_observation *out)
{
    if (!owner || !out || ml_at_interrupt_context() || rpi5_pm_base == 0 ||
        !rpi5_pcie_watchdog_gate_claim(&rpi5_usb_console_wdog_gate, owner)) {
        return false;
    }
    const struct rpi5_pcie_watchdog_console_io io = {
        NULL, rpi5_usb_console_wdog_active, rpi5_pcie_wdog_route,
        rpi5_pcie_wdog_count, rpi5_pcie_wdog_counter,
    };
    uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
    bool ok = rpi5_pcie_watchdog_console_init(
        &rpi5_usb_console_wdog_lease, &io, frequency) == 0 &&
        rpi5_pcie_watchdog_console_begin(
            &rpi5_usb_console_wdog_lease, out) == 0;
    rpi5_pcie_watchdog_gate_leave(&rpi5_usb_console_wdog_gate);
    return ok;
}

bool
pe_rpi5_watchdog_check_usb_console(const void *owner)
{
    if (!owner || ml_at_interrupt_context() ||
        !rpi5_pcie_watchdog_gate_owner(&rpi5_usb_console_wdog_gate, owner)) {
        return false;
    }
    bool ok = rpi5_pcie_watchdog_console_check(
        &rpi5_usb_console_wdog_lease) == 0;
    rpi5_pcie_watchdog_gate_leave(&rpi5_usb_console_wdog_gate);
    return ok;
}
