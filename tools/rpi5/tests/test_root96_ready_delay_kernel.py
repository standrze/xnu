# SPDX-License-Identifier: BSD-2-Clause
"""Actual v2 PE bodies with explicit clock/MMIO/output doubles, never hardware."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import build_root96_ready_delay_kernel as builder

BASE = builder.ROOT / 'build/rpi5/root96-ready-delay-kernel-20261013-final'


class ReadinessDelayTests(unittest.TestCase):
    def test_closed_sources_and_exact_isolated_transform(self):
        m = json.loads((BASE / 'manifest.json').read_text())
        self.assertEqual((BASE / 'pe_fiq.c').read_text(),
            builder.transform((builder.prior.BASE / 'pe_fiq.c').read_text()))
        for key in ('inputs_sha256', 'generated_sha256'):
            self.assertTrue(m[key])
            for path, digest in m[key].items():
                self.assertEqual(builder.audit.sha(Path(path)), digest, path)
        self.assertEqual(m['first_notice_minimum_post_enable_seconds'], 5)
        self.assertEqual(m['terminal_deadline_seconds'], 180)
        self.assertFalse(m['deadline_extended'])
        self.assertFalse(m['arbitrary_console_serialization'])
        self.assertIn(str(Path(__file__).resolve()), m['inputs_sha256'])

    def test_actual_body_early_reload_threshold_and_boundaries(self):
        source = builder.transform((builder.prior.BASE / 'pe_fiq.c').read_text())
        start = source.index('bool\npe_rpi5_watchdog_enable_terminal(void)')
        end = source.index('#if RPI5_PCI_WDOG_LEASE\n#include', start)
        defines = '\n'.join(line for line in source.splitlines() if line.startswith('#define RPI5_') and any(
            word in line.split()[1] for word in ('WDOG', 'PM_RSTC', 'PM_WDOG', 'PM_FULL_RESET')))
        preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include <stdio.h>
#define RPI5_PCI_WDOG_LEASE 1
#define DSB_SY 0
#define __builtin_arm_dsb(a) ((void)(a))
static uint64_t frequency, counter, rpi5_pm_base, rpi5_wdog_deadline;
static uint64_t rpi5_wdog_last_counter, rpi5_wdog_reload_ticks;
static uint64_t rpi5_wdog_soak_start_counter, rpi5_wdog_soak_grace_ticks;
static uint64_t rpi5_wdog_terminal_report_after, enable_time;
static unsigned rpi5_wdog_reloads, rpi5_wdog_soak_seconds, writes, notices, at_last_notice;
static bool rpi5_wdog_terminal_enabled, rpi5_wdog_terminal_reported;
static uint32_t rstc;
static void kprintf(const char *format, ...) {
    if (strstr(format, "WATCHDOG_READY")) {
        va_list ap; va_start(ap, format); assert(va_arg(ap, unsigned) == 180); va_end(ap);
        assert(writes > 0 && rpi5_wdog_terminal_enabled && rpi5_wdog_terminal_reported);
        assert(counter == rpi5_wdog_last_counter && counter < rpi5_wdog_deadline);
        assert(counter >= enable_time && counter-enable_time >= frequency*5);
        assert(counter >= rpi5_wdog_terminal_report_after); notices++; at_last_notice = writes;
    } else assert(strstr(format, "WATCHDOG_KICK"));
}
static uint64_t clock_read(const char *name) {
    assert(!strcmp(name,"CNTFRQ_EL0") || !strcmp(name,"CNTVCT_EL0"));
    return !strcmp(name,"CNTFRQ_EL0") ? frequency : counter;
}
#define __builtin_arm_rsr64(name) clock_read(name)
static uint32_t rpi5_mmio_read32(uint64_t base, unsigned offset) {
    assert(base == 1 && offset == 0x1c); return rstc;
}
static void rpi5_mmio_write32(uint64_t base, unsigned offset, uint32_t value) {
    assert(base == 1 && offset == 0x24 && value == UINT32_C(0x5a0f0000)); writes++;
}
static void reset(void) {
    frequency=1000;counter=enable_time=10000;rpi5_pm_base=1;rpi5_wdog_deadline=20000;
    rpi5_wdog_last_counter=1;rpi5_wdog_reload_ticks=5000;
    rpi5_wdog_soak_start_counter=rpi5_wdog_soak_grace_ticks=0;
    rpi5_wdog_terminal_report_after=0;rpi5_wdog_reloads=rpi5_wdog_soak_seconds=0;
    writes=notices=at_last_notice=0;rpi5_wdog_terminal_enabled=rpi5_wdog_terminal_reported=false;rstc=0x20;
}
'''
        main = r'''
int main(void) {
    reset();assert(pe_rpi5_watchdog_enable_terminal());
    assert(rpi5_wdog_deadline==190000&&rpi5_wdog_terminal_report_after==15000);
    /* An old boot counter permits a reload immediately, but not the notice. */
    rpi5_watchdog_service_unlocked(true);assert(writes==1&&notices==0);
    counter=14999;rpi5_watchdog_service_unlocked(true);assert(writes==1&&notices==0);
    counter=15000;rpi5_watchdog_service_unlocked(true);assert(writes==2&&notices==1&&at_last_notice==2);
    for(unsigned second=10;second<180;second+=5) {
        counter=10000+second*1000;rpi5_watchdog_service_unlocked(true);assert(notices==1);
    }
    unsigned before=writes;counter=190000;assert(!pe_rpi5_watchdog_terminal_active());
    rpi5_watchdog_service_unlocked(true);counter+=15000;rpi5_watchdog_service_unlocked(true);
    assert(writes==before&&notices==1&&rpi5_wdog_deadline==190000);
    /* The first eligible reload can occur AFTER the threshold, not at it. */
    reset();rpi5_wdog_last_counter=6000;rpi5_wdog_reloads=7;
    assert(pe_rpi5_watchdog_enable_terminal());counter=11000;rpi5_watchdog_service_unlocked(true);
    assert(writes==1&&notices==0);counter=15000;rpi5_watchdog_service_unlocked(true);assert(notices==0);
    counter=16000;rpi5_watchdog_service_unlocked(true);assert(writes==2&&notices==1);
    /* Zero/unpublished threshold must not pass, even with the legacy flag set. */
    reset();assert(pe_rpi5_watchdog_enable_terminal());rpi5_wdog_terminal_report_after=0;
    counter=20000;rpi5_watchdog_service_unlocked(true);assert(writes==1&&!notices);
    reset();assert(pe_rpi5_watchdog_enable_terminal());rstc=0;counter=15000;
    rpi5_watchdog_service_unlocked(true);assert(!writes&&!notices&&!rpi5_wdog_deadline);
    reset();assert(pe_rpi5_watchdog_enable_terminal());counter=rpi5_wdog_deadline;
    rpi5_watchdog_service_unlocked(true);assert(!writes&&!notices);
    /* Rejected enable paths cannot publish readiness. */
    for(unsigned bad=0;bad<7;bad++) {
        reset();
        if(bad==0)rpi5_pm_base=0;if(bad==1)frequency=0;if(bad==2)frequency=UINT64_MAX;
        if(bad==3)counter=UINT64_MAX-179999;if(bad==4)rpi5_wdog_soak_seconds=1;
        if(bad==5)rstc=0;if(bad==6)rpi5_wdog_deadline=0;
        assert(!pe_rpi5_watchdog_enable_terminal()&&!rpi5_wdog_terminal_report_after&&!writes&&!notices);
    }
    reset();counter=enable_time=UINT64_MAX-180000;
    assert(pe_rpi5_watchdog_enable_terminal()&&rpi5_wdog_deadline==UINT64_MAX);
    assert(rpi5_wdog_terminal_report_after==UINT64_MAX-175000);
    uint64_t threshold=rpi5_wdog_terminal_report_after;
    assert(!pe_rpi5_watchdog_enable_terminal()&&rpi5_wdog_terminal_report_after==threshold);
    puts("READY_V2_PASS EARLY_RELOAD_SUPPRESSED=1 THRESHOLD_BOUNDARY=1 DEADLINE_UNCHANGED=1 MMIO_CLOCK_DOUBLES");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'ready.c').write_text(preamble + defines + '\n' + source[start:end] + main)
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',p/'ready.c','-o',p/'ready'],
                check=True,capture_output=True)
            result=subprocess.run([p/'ready'],check=True,capture_output=True)
            self.assertEqual(result.stderr,b'')
            self.assertEqual(result.stdout,b'READY_V2_PASS EARLY_RELOAD_SUPPRESSED=1 THRESHOLD_BOUNDARY=1 DEADLINE_UNCHANGED=1 MMIO_CLOCK_DOUBLES\n')


if __name__ == '__main__':
    unittest.main()
