/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_watchdog_console_lease.h"

#define COUNT_MASK UINT32_C(0xfffff)
#define MINIMUM (2u << 16)
#define MAXIMUM (15u << 16)
#define MAX_CHECKS UINT32_C(1048576)

static int
fail(struct rpi5_pcie_watchdog_console_lease *lease)
{
    lease->state = RPI5_PCIE_CONSOLE_WDOG_QUARANTINED;
    return -1;
}

static int
valid_route(uint32_t value)
{
    return value != UINT32_MAX && (value & UINT32_C(0x30)) == UINT32_C(0x20);
}

static int
valid_countdown(uint32_t value)
{
    value &= COUNT_MASK;
    return value > MINIMUM && value <= MAXIMUM;
}

int
rpi5_pcie_watchdog_console_init(
    struct rpi5_pcie_watchdog_console_lease *lease,
    const struct rpi5_pcie_watchdog_console_io *io, uint64_t frequency)
{
    if (!lease || !io || !io->terminal_active || !io->read_route ||
        !io->read_countdown || !io->counter || !frequency ||
        lease->state != RPI5_PCIE_CONSOLE_WDOG_EMPTY) {
        return -1;
    }
    lease->io = *io;
    lease->frequency = frequency;
    lease->start = 0;
    lease->last_counter = 0;
    lease->first_countdown = 0;
    lease->last_countdown = 0;
    lease->checks = 0;
    lease->callbacks = 0;
    lease->state = RPI5_PCIE_CONSOLE_WDOG_READY;
    return 0;
}

int
rpi5_pcie_watchdog_console_begin(
    struct rpi5_pcie_watchdog_console_lease *lease,
    struct rpi5_pcie_watchdog_console_observation *output)
{
    if (!lease || !output ||
        lease->state != RPI5_PCIE_CONSOLE_WDOG_READY) {
        return -1;
    }
    lease->state = RPI5_PCIE_CONSOLE_WDOG_BUSY;
    struct rpi5_pcie_watchdog_console_observation result;
    uint32_t route, countdown;
    uint64_t start, now;
#define STEP(call) do { \
    if ((call)) return fail(lease); \
    lease->callbacks++; \
} while (0)
    STEP(lease->io.terminal_active(lease->io.context) ? 0 : -1);
    STEP(lease->io.counter(lease->io.context, &start));
    STEP(lease->io.read_route(lease->io.context, &route));
    if (!valid_route(route)) return fail(lease);
    STEP(lease->io.read_countdown(lease->io.context, &countdown));
    if (countdown == UINT32_MAX || !valid_countdown(countdown)) {
        return fail(lease);
    }
    STEP(lease->io.terminal_active(lease->io.context) ? 0 : -1);
    STEP(lease->io.counter(lease->io.context, &now));
    if (now < start || now - start > lease->frequency) return fail(lease);
#undef STEP
    lease->start = start;
    lease->last_counter = now;
    lease->first_countdown = countdown & COUNT_MASK;
    lease->last_countdown = countdown & COUNT_MASK;
    lease->state = RPI5_PCIE_CONSOLE_WDOG_ACTIVE;
    result.start = start;
    result.sampled_counter = now;
    result.countdown = countdown & COUNT_MASK;
    *output = result;
    return 0;
}

int
rpi5_pcie_watchdog_console_check(
    struct rpi5_pcie_watchdog_console_lease *lease)
{
    if (!lease || lease->state != RPI5_PCIE_CONSOLE_WDOG_ACTIVE) {
        return -1;
    }
    if (lease->checks >= MAX_CHECKS) return fail(lease);
    lease->state = RPI5_PCIE_CONSOLE_WDOG_BUSY;
    uint32_t route, countdown;
    uint64_t before, after;
#define STEP(call) do { \
    if ((call)) return fail(lease); \
    lease->callbacks++; \
} while (0)
    STEP(lease->io.terminal_active(lease->io.context) ? 0 : -1);
    STEP(lease->io.counter(lease->io.context, &before));
    if (before < lease->last_counter) return fail(lease);
    STEP(lease->io.read_route(lease->io.context, &route));
    if (!valid_route(route)) return fail(lease);
    STEP(lease->io.read_countdown(lease->io.context, &countdown));
    if (countdown == UINT32_MAX || !valid_countdown(countdown)) {
        return fail(lease);
    }
    STEP(lease->io.terminal_active(lease->io.context) ? 0 : -1);
    STEP(lease->io.counter(lease->io.context, &after));
    if (after < before) return fail(lease);
#undef STEP
    lease->last_counter = after;
    lease->last_countdown = countdown & COUNT_MASK;
    lease->checks++;
    lease->state = RPI5_PCIE_CONSOLE_WDOG_ACTIVE;
    return 0;
}
