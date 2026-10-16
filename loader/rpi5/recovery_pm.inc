/* SPDX-License-Identifier: BSD-2-Clause */
/* The real standalone provider/protocol, also executed under host doubles. */
#if !RPI5_RECOVERY_PM_PROBE
#error "Recovery PM protocol requires its separate standalone diagnostic"
#endif
#include "recovery_pm.h"
static struct {
    uint64_t frequency;
    uint32_t write_attempts, last_route, phase;
} recovery_pm;
static struct rpi5_pcie_watchdog_lease recovery_lease;
static int recovery_record(unsigned, const struct rpi5_recovery_observation *);

static int recovery_context(void *context)
{
    return context != &recovery_pm || recovery_pm.phase != 1 ||
        recovery_pm.frequency < 1000000 || recovery_pm.frequency > 1000000000 ? -1 : 0;
}
static int recovery_read_route(void *context, uint32_t *out)
{
    if (!out || recovery_context(context)) return -1;
    *out = recovery_pm.last_route = rpi5_recovery_route();
    return 0; /* A CPU abort/hang does not return an invented error. */
}
static int recovery_read_count(void *context, uint32_t *out)
{
    if (!out || recovery_context(context)) return -1;
    *out = rpi5_recovery_countdown();
    return 0;
}
static int recovery_write(void *context, uint32_t value)
{
    if (recovery_context(context) || recovery_pm.write_attempts || value != UINT32_C(0x5a0f0000)) return -1;
    recovery_pm.write_attempts = 1; /* Irreversible, even if the store faults. */
    rpi5_recovery_write_countdown(value);
    return 0;
}
static int recovery_order(void *context)
{
    if (recovery_context(context)) return -1;
    rpi5_recovery_order();
    return 0;
}
static int recovery_counter(void *context, uint64_t *out)
{
    if (!out || recovery_context(context)) return -1;
    *out = rpi5_recovery_counter();
    return 0;
}
static int recovery_wait(uint64_t minimum, uint64_t floor)
{
    uint64_t start = rpi5_recovery_counter(), last = start;
    if (start < floor) return -1;
    /* No sleep/interrupt/secondary CPU or timer servicing. Even a stopped
     * architectural counter terminates after a finite one-million samples. */
    for (unsigned i = 0; i < 1000000; i++) {
        uint64_t now = rpi5_recovery_counter();
        if (now < last) return -1;
        if (now-start >= minimum) return 0;
        last = now;
    }
    return -1;
}
static int recovery_run(struct rpi5_recovery_observation *out)
{
    if (!out || recovery_pm.phase || recovery_pm.frequency < 1000000 || recovery_pm.frequency > 1000000000)
        return -1;
    recovery_pm.phase = 1; /* One invocation until reset; no reentry/retry. */
    const struct rpi5_pcie_watchdog_io io = {&recovery_pm, recovery_read_route, recovery_read_count,
        recovery_write, recovery_order, recovery_counter};
    struct rpi5_recovery_observation result = {0};
    uint64_t before, after, minimum = (recovery_pm.frequency+499)/500;
    if (rpi5_pcie_watchdog_init(&recovery_lease, &io, recovery_pm.frequency) ||
        rpi5_pcie_watchdog_begin(&recovery_lease, &result.watchdog)) goto failed;
    result.frequency = recovery_pm.frequency;
    result.route = recovery_pm.last_route;
    result.final_countdown = recovery_lease.last_countdown;
    if (recovery_record(RPI5_RECOVERY_ARMED, &result) || recovery_counter(&recovery_pm, &before) ||
        before < recovery_lease.last_counter || recovery_wait(minimum, before) ||
        recovery_counter(&recovery_pm, &after) || after < before || after-before < minimum ||
        after-before > recovery_pm.frequency || rpi5_pcie_watchdog_check(&recovery_lease)) goto failed;
    result.waited_ticks = after-before;
    result.final_countdown = recovery_lease.last_countdown;
    result.checks = recovery_lease.checks;
    if (recovery_record(RPI5_RECOVERY_CHECKED, &result)) goto failed;
    recovery_pm.phase = 2; /* Checked and about to park, NOT reset completed. */
    *out = result;
    return 0;
failed:
    recovery_pm.phase = 3;
    recovery_lease.state = RPI5_PCIE_WDOG_QUARANTINED;
    return -1; /* Never restore/reload/reroute/clean up, even after a store. */
}
