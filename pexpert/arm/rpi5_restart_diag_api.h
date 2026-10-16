/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RESTART_DIAG_API_H
#define RPI5_RESTART_DIAG_API_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct rpi5_restart_diag_snapshot {
    uint64_t cntvct_before, cntvct, cntfrq, terminal_deadline;
    uint32_t watchdog_count_before, watchdog_remaining_ticks, full_reset_route;
    uint32_t watchdog_nominal_hz, watchdog_rate_bound_proven;
};
/* One nonblocking acquisition of the EXISTING watchdog service gate. Never
 * claim its monotonic owner, reload, change deadline, mask IRQs or wait on a
 * halted peer. Failure leaves output unchanged. Raw countdown encoding and
 * nominal65536 units/second do NOT establish a measured maximum clock rate;
 * watchdog_rate_bound_proven is deliberately zero for this profile. */
int rpi5_restart_diag_snapshot(struct rpi5_restart_diag_snapshot *);
/* Existing initialized PL011 Device provider only, fresh retained-FDT nominal
 * divisor match. At most256 bytes/100ms/1,000,000 polls for the WHOLE message.
 * DR stores only: no RX, UART configuration, IRQ/DMA or console locks. Zero
 * means all bytes were accepted and BUSY cleared, not exclusive delivery;
 * concurrent writers may interleave and MUST cause protocol rejection.
 * Any error can follow partial transmission; no automatic retry. */
int rpi5_restart_diag_uart(const char *, size_t);
/* Implemented by the separately composed opt-in platform policy. Called once
 * from the existing delayed WATCHDOG_READY branch, under its service gate.
 * Must not recursively call snapshot/acquire that gate. */
void rpi5_restart_diagnostic_boot_ready(void);
#ifdef __cplusplus
}
#endif
#endif
