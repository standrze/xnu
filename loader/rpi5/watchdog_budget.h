/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_WATCHDOG_BUDGET_H
#define RPI5_WATCHDOG_BUDGET_H
#include <stdint.h>
#include <stddef.h>
/* Pure authorization budget, not an MMIO driver. One immutable workload.
 * Strict progress and a finite renewal count bound servicing even if the
 * counter stalls. Caller separately validates clock, hardware and ownership. */
struct rpi5_watchdog_budget {
    uint64_t deadline, last_counter;
    size_t total, completed;
    unsigned remaining;
};
static inline int rpi5_watchdog_budget_step(struct rpi5_watchdog_budget *b,
    uint64_t now, size_t completed, size_t total)
{
    if (!b || !b->remaining || !total || total != b->total ||
        completed <= b->completed || completed > total ||
        now < b->last_counter || now >= b->deadline) return 0;
    b->last_counter = now;
    b->completed = completed;
    --b->remaining;
    return 1;
}
#endif
