/* SPDX-License-Identifier: BSD-2-Clause
 * Exact candidate policy with one explicitly interposed pre-reset diagnostic.
 * The original binding, EL, irreversible CAS, version and feature decisions
 * execute before this hook. The fixed original SYSTEM_RESET leaf is unchanged.
 */
#define rpi5_restart_psci_reset rpi5_restart_diagnostic_reset
#include "psci_restart_candidate.c"
#undef rpi5_restart_psci_reset
#include "psci_restart_diagnostic.h"
#include "pexpert/arm/rpi5_restart_diag_api.h"

extern uint64_t rpi5_restart_psci_reset(void);

static const char ready[] =
    "\nRPI5XNU:RESTART:READY OPTIN=1 PSCI=00010001 RESET_SUPPORTED=1 WATCHDOG_UNCHANGED\n";
static const char returned[] = "\nRPI5XNU:RESTART:RETURNED NO_RESET_PROVEN\n";

static void literal(char *out, size_t *used, const char *text)
{
    while (*text) out[(*used)++] = *text++;
}

static void hex(char *out, size_t *used, uint64_t value, unsigned digits)
{
    static const char alphabet[] = "0123456789abcdef";
    for (unsigned i = digits; i; i--) out[(*used)++] = alphabet[(value >> (4 * (i-1))) & 15];
}

int rpi5_restart_diagnostic_ready(const void *tree, size_t bytes)
{
    uintptr_t p = (uintptr_t)tree;
    if (!tree || bytes < 40 || bytes > 2u * 1024u * 1024u || p > UINTPTR_MAX - bytes ||
        binding(tree, bytes) || rpi5_restart_current_el() != 4 ||
        (uint32_t)rpi5_restart_psci_version() != UINT32_C(0x00010001) ||
        (uint32_t)rpi5_restart_psci_feature() != 0) return 0;
    /* No PM snapshot here: caller is the existing successful-reload owner.
     * Readiness is eligibility only, never an attempted/successful reset. */
    return rpi5_restart_diag_uart(ready, sizeof(ready)-1) == 0;
}

uint64_t rpi5_restart_diagnostic_reset(void)
{
    struct rpi5_restart_diag_snapshot s;
    if (rpi5_restart_diag_snapshot(&s) != 0 ||
        s.cntvct < s.cntvct_before || !s.cntfrq || s.cntvct >= s.terminal_deadline ||
        s.watchdog_count_before > UINT32_C(0xfffff) || !s.watchdog_remaining_ticks ||
        s.watchdog_remaining_ticks > s.watchdog_count_before ||
        s.full_reset_route != 1 || s.watchdog_nominal_hz != 65536 ||
        s.watchdog_rate_bound_proven != 0) return UINT64_MAX;
    /* Exact bounded formatter, no allocator, stdio, video or console locks.
     * This reports a NOMINAL countdown. RATE_BOUND=0 prevents metadata from
     * claiming an independently qualified maximum physical oscillator rate. */
    char line[256]; size_t n = 0;
    literal(line,&n,"\nRPI5XNU:RESTART:PRE_SMC COUNT=");hex(line,&n,s.watchdog_remaining_ticks,8);
    literal(line,&n," COUNTER=");hex(line,&n,s.cntvct,16);
    literal(line,&n," FREQ=");hex(line,&n,s.cntfrq,16);
    literal(line,&n," DEADLINE=");hex(line,&n,s.terminal_deadline,16);
    literal(line,&n," NOMINAL_HZ=00010000 RATE_BOUND=0\n");
    if (rpi5_restart_diag_uart(line,n) != 0) return UINT64_MAX;
    uint64_t result = rpi5_restart_psci_reset();
    /* Every return is failure, including zero. A failed diagnostic write
     * cannot turn a returned SMC into success; host timing alone cannot do so. */
    (void)rpi5_restart_diag_uart(returned,sizeof(returned)-1);
    return result;
}
