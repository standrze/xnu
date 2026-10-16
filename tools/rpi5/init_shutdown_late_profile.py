# SPDX-License-Identifier: BSD-2-Clause
"""Distinct bounded late PID1 reports; the frozen shutdown policy is unchanged.

Scheduling deferral reduces startup contention; it does not create UART line
atomicity. Each report still describes a freshly observed real signal mask.
"""
from pathlib import Path
from . import init_shutdown_profile as prior

ROOT=prior.ROOT;ORIGINAL=prior.ORIGINAL;ORIGINAL_SHA=prior.ORIGINAL_SHA
BODY=prior.BODY
READY=prior.READY
MAX_REPORTS=3
BODY_SHA='6df1c7e0d62ed6423460c0bcccb6d666728524ada763e4e4270017dfae53f8e0'
sha=prior.sha

def replace(raw,old,new):
    if raw.count(old)!=1:raise ValueError('Exact late-readiness derivation boundary')
    return raw.replace(old,new,1)

def body():
    if sha(BODY)!=BODY_SHA:raise ValueError('Frozen nonexiting PID1 policy required')
    raw=BODY.read_text()
    raw=replace(raw,'#define INIT_WNOHANG 1', '''#define INIT_WNOHANG 1
static uint32_t init_expected_mask;
static unsigned init_ready_reports;
static unsigned init_successful_sleeps;''')
    raw=replace(raw,'static void init_pause(void)', '''/* Called only following a completed one-second select, never on EINTR.
 * A global cap survives shell respawns. No publication follows observed TERM.
 * This is not a serialization guarantee against independent kernel writers. */
static void init_report_ready(void)
{
    uint32_t actual = 0;
    init_check_shutdown();
    if (rt_call(48, INIT_SIG_BLOCK, 0, (long)&actual, 0, 0, 0) != 0 ||
            actual != init_expected_mask)
        init_stopped("RPI5XNU:INIT:STOPPING MASK_VERIFY_FAILED\\n");
    init_check_shutdown();
    if (init_ready_reports < 3) {
        init_ready_reports++;
        rt_put(1, "RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION\\n");
    }
}

static void init_pause(void)''')
    raw=replace(raw,'''    if (result != 0 && result != -4)
        init_stopped("RPI5XNU:INIT:STOPPING SLEEP_FAILED\\n");''', '''    if (result != 0 && result != -4)
        init_stopped("RPI5XNU:INIT:STOPPING SLEEP_FAILED\\n");
    if (result == 0) {
        if (init_successful_sleeps < 3) init_successful_sleeps++;
        if (init_ready_reports < 3) init_report_ready();
    }''')
    raw=replace(raw,'    uint32_t block = INIT_TERM_MASK, saved = 0, actual = 0;',
        '    uint32_t block = INIT_TERM_MASK, saved = 0, actual = 0;\n    init_ready_reports = init_successful_sleeps = 0;')
    raw=replace(raw,'''    init_check_shutdown();
    long console''','''    init_expected_mask = saved | INIT_TERM_MASK;
    init_check_shutdown();
    long console''')
    raw=replace(raw,'''    rt_put(1, "RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION\\n");
    rt_put(1, "RPI5XNU:INIT:READY\\n");''', '''    /* Do not count interrupted select calls as a completed delay. */
    while (!init_successful_sleeps) init_pause();
    rt_put(1, "RPI5XNU:INIT:READY\\n");''')
    return raw

def derive(raw):
    original=prior.derive(raw)
    return replace(original,BODY.read_text(),body())

def sources():
    return [*prior.sources(),Path(__file__).resolve(),
        ROOT/'tools/rpi5/tests/init_shutdown_late_host.c',ROOT/'tools/rpi5/tests/test_init_shutdown_late.py']
