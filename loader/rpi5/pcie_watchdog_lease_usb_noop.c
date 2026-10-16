/* SPDX-License-Identifier: BSD-2-Clause */
/* Diagnostic-only finite budget for the USB No-Op composition. The inherited
 * controller path consumes 64,868 checks before USB DMA begins, so its normal
 * 65,536-check translation unit cannot cover an actual BME lease. Time and
 * countdown bounds remain unchanged; other profiles retain the default. */
#include "pcie_watchdog_lease.h"

#define COUNT_MASK UINT32_C(0xfffff)
#define INTERVAL (15u << 16)
#define MINIMUM (2u << 16)
#define MAX_CHECKS UINT32_C(131072)

static int fail(struct rpi5_pcie_watchdog_lease *s)
{
    s->state = RPI5_PCIE_WDOG_QUARANTINED;
    return -1;
}
static int valid_route(uint32_t value)
{
    return value != UINT32_MAX && (value & 0x30) == 0x20;
}

int rpi5_pcie_watchdog_init(struct rpi5_pcie_watchdog_lease *s,
    const struct rpi5_pcie_watchdog_io *io, uint64_t frequency)
{
    if (!s || !io || !io->read_route || !io->read_countdown ||
        !io->write_countdown || !io->order || !io->counter || !frequency ||
        frequency > UINT64_MAX / 12 || s->state != RPI5_PCIE_WDOG_EMPTY)
        return -1;
    s->io.context = io->context; s->io.read_route = io->read_route;
    s->io.read_countdown = io->read_countdown;
    s->io.write_countdown = io->write_countdown;
    s->io.order = io->order; s->io.counter = io->counter;
    s->frequency = frequency;
    s->start = 0; s->deadline = 0; s->last_counter = 0;
    s->first_countdown = 0; s->last_countdown = 0;
    s->checks = 0; s->callbacks = 0;
    s->state = RPI5_PCIE_WDOG_READY;
    return 0;
}

int rpi5_pcie_watchdog_begin(struct rpi5_pcie_watchdog_lease *s,
    struct rpi5_pcie_watchdog_observation *out)
{
    if (!s || !out || s->state != RPI5_PCIE_WDOG_READY) return -1;
    s->state = RPI5_PCIE_WDOG_BUSY;
    struct rpi5_pcie_watchdog_observation result;
    uint32_t route, prior, armed;
    uint64_t start, now;
#define STEP(call) do { if ((call)) return fail(s); s->callbacks++; } while (0)
    STEP(s->io.counter(s->io.context, &start));
    if (start > UINT64_MAX - 12 * s->frequency) return fail(s);
    STEP(s->io.read_route(s->io.context, &route));
    if (!valid_route(route)) return fail(s);
    STEP(s->io.read_countdown(s->io.context, &prior));
    if (prior == UINT32_MAX || (prior & COUNT_MASK) <= MINIMUM)
        return fail(s);
    STEP(s->io.write_countdown(s->io.context,
        UINT32_C(0x5a000000) | INTERVAL));
    STEP(s->io.order(s->io.context));
    STEP(s->io.read_route(s->io.context, &route));
    if (!valid_route(route)) return fail(s);
    STEP(s->io.read_countdown(s->io.context, &armed));
    if (armed == UINT32_MAX || (armed & COUNT_MASK) < (14u << 16) ||
        (armed & COUNT_MASK) > INTERVAL) return fail(s);
    STEP(s->io.counter(s->io.context, &now));
    if (now < start || now - start > s->frequency) return fail(s);
#undef STEP
    s->start = start; s->deadline = start + 12 * s->frequency;
    s->last_counter = now;
    s->first_countdown = armed & COUNT_MASK;
    s->last_countdown = armed & COUNT_MASK;
    s->state = RPI5_PCIE_WDOG_ARMED;
    result.start = start; result.deadline = s->deadline;
    result.sampled_counter = now;
    result.prior_countdown = prior & COUNT_MASK;
    result.armed_countdown = armed & COUNT_MASK;
    *out = result;
    return 0;
}

int rpi5_pcie_watchdog_check(struct rpi5_pcie_watchdog_lease *s)
{
    if (!s || s->state != RPI5_PCIE_WDOG_ARMED) return -1;
    if (s->checks >= MAX_CHECKS) return fail(s);
    s->state = RPI5_PCIE_WDOG_BUSY;
    uint32_t route, count;
    uint64_t before, after;
#define STEP(call) do { if ((call)) return fail(s); s->callbacks++; } while (0)
    STEP(s->io.counter(s->io.context, &before));
    if (before < s->last_counter || before >= s->deadline) return fail(s);
    STEP(s->io.read_route(s->io.context, &route));
    if (!valid_route(route)) return fail(s);
    STEP(s->io.read_countdown(s->io.context, &count));
    if (count == UINT32_MAX) return fail(s);
    count &= COUNT_MASK;
    if (count <= MINIMUM || count > s->last_countdown) return fail(s);
    if (before - s->start >= (s->frequency + 999) / 1000 &&
        count >= s->first_countdown) return fail(s);
    STEP(s->io.counter(s->io.context, &after));
    if (after < before || after >= s->deadline) return fail(s);
#undef STEP
    s->last_counter = after; s->last_countdown = count; s->checks++;
    s->state = RPI5_PCIE_WDOG_ARMED;
    return 0;
}
