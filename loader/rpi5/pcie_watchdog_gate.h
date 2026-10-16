/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_WATCHDOG_GATE_H
#define RPI5_PCIE_WATCHDOG_GATE_H
#include <stdint.h>

/* Shared by EVERY normal watchdog service path and the diagnostic claimant.
 * Nonblocking: IRQ preemption/recursion/other-CPU contention returns failure,
 * never spins behind a potentially faulting PM access. Zeroed stable storage.
 * Successful enter/claim holds the gate until leave. owner is monotonic and
 * cannot be cleared; a failed physical begin still suppresses all servicing. */
struct rpi5_pcie_watchdog_gate { uint32_t busy; const void *owner; };
static inline int rpi5_pcie_watchdog_gate_lock(struct rpi5_pcie_watchdog_gate *gate)
{
    uint32_t expected = 0;
    return __atomic_compare_exchange_n(&gate->busy, &expected, 1, 0,
        __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
}
static inline void rpi5_pcie_watchdog_gate_leave(struct rpi5_pcie_watchdog_gate *gate)
{
    __atomic_store_n(&gate->busy, 0, __ATOMIC_RELEASE);
}
static inline int rpi5_pcie_watchdog_gate_service(struct rpi5_pcie_watchdog_gate *gate)
{
    if (__atomic_load_n(&gate->owner, __ATOMIC_ACQUIRE) || !rpi5_pcie_watchdog_gate_lock(gate)) return 0;
    if (__atomic_load_n(&gate->owner, __ATOMIC_ACQUIRE)) {
        rpi5_pcie_watchdog_gate_leave(gate);
        return 0;
    }
    return 1;
}
static inline int rpi5_pcie_watchdog_gate_claim(struct rpi5_pcie_watchdog_gate *gate, const void *owner)
{
    if (!owner || !rpi5_pcie_watchdog_gate_lock(gate)) return 0;
    if (__atomic_load_n(&gate->owner, __ATOMIC_ACQUIRE)) {
        rpi5_pcie_watchdog_gate_leave(gate);
        return 0;
    }
    __atomic_store_n(&gate->owner, owner, __ATOMIC_RELEASE);
    return 1;
}
static inline int rpi5_pcie_watchdog_gate_owner(struct rpi5_pcie_watchdog_gate *gate, const void *owner)
{
    if (!owner || !rpi5_pcie_watchdog_gate_lock(gate)) return 0;
    if (__atomic_load_n(&gate->owner, __ATOMIC_ACQUIRE) != owner) {
        rpi5_pcie_watchdog_gate_leave(gate);
        return 0;
    }
    return 1;
}
#endif
