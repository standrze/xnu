# SPDX-License-Identifier: BSD-2-Clause
"""Actual modified PE bodies, with explicit native clock/MMIO/output doubles."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import build_root96_ready_kernel as builder

BASE = builder.ROOT / 'build/rpi5/root96-ready-kernel-20261013-checked'


class ReadinessKernelTests(unittest.TestCase):
    def test_exact_source_change_and_linked_receipt(self):
        m = json.loads((BASE / 'manifest.json').read_text())
        self.assertEqual((BASE / 'pe_fiq.c').read_text(), builder.transform((builder.BASE / 'pe_fiq.c').read_text()))
        for key in ('inputs_sha256', 'generated_sha256'):
            for path, digest in m[key].items():
                self.assertEqual(builder.audit.sha(Path(path)), digest, path)
        self.assertEqual(m['terminal_deadline_seconds'], 180)
        self.assertIn(builder.MARKER.encode(), Path(m['kernel']).read_bytes())
        self.assertNotIn(b'RPI5XNU:TERMINAL:WATCHDOG SECONDS=%u', Path(m['kernel']).read_bytes())

    def test_real_deadline_reload_and_single_post_reload_message(self):
        source = (BASE / 'pe_fiq.c').read_text()
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
static unsigned rpi5_wdog_reloads, rpi5_wdog_soak_seconds, writes, notices;
static bool rpi5_wdog_terminal_enabled, rpi5_wdog_terminal_reported;
static uint32_t rstc = 0x20;
static void kprintf(const char *format, ...) {
    if (strstr(format, "WATCHDOG_READY")) {
        va_list ap; va_start(ap, format); assert(va_arg(ap, unsigned) == 180); va_end(ap);
        assert(writes == 1 && rpi5_wdog_terminal_enabled && rpi5_wdog_terminal_reported);
        assert(counter < rpi5_wdog_deadline); notices++;
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
'''
        main = r'''
int main(void) {
    frequency = 1000; counter = 1000; rpi5_pm_base = 0; rpi5_wdog_deadline = 2000;
    assert(!pe_rpi5_watchdog_enable_terminal());
    rpi5_pm_base = 1; frequency = 0; assert(!pe_rpi5_watchdog_enable_terminal());
    frequency = UINT64_MAX; assert(!pe_rpi5_watchdog_enable_terminal());
    frequency = 1000; counter = UINT64_MAX - 179999; assert(!pe_rpi5_watchdog_enable_terminal());
    counter = 1000; assert(pe_rpi5_watchdog_enable_terminal());
    assert(rpi5_wdog_deadline == 181000 && writes == 0 && notices == 0);
    assert(!pe_rpi5_watchdog_enable_terminal());
    rpi5_wdog_last_counter = 1000; rpi5_wdog_reload_ticks = 5000;
    counter = 5999; rpi5_watchdog_service_unlocked(true);
    assert(writes == 0 && notices == 0 && !rpi5_wdog_terminal_reported);
    for (unsigned second = 5; second < 180; second += 5) {
        counter = 1000 + 1000 * second; rpi5_watchdog_service_unlocked(true);
        assert(writes == second / 5 && notices == 1 && rpi5_wdog_last_counter == counter);
    }
    counter = 181000; assert(!pe_rpi5_watchdog_terminal_active());
    rpi5_watchdog_service_unlocked(true); counter = 196000; rpi5_watchdog_service_unlocked(true);
    assert(writes == 35 && notices == 1);
    /* No message if the reset route disappears before the first reload. */
    rpi5_wdog_terminal_enabled = false; rpi5_wdog_terminal_reported = false;
    rpi5_wdog_deadline = 2000; counter = 1000;
    assert(pe_rpi5_watchdog_enable_terminal());
    rpi5_wdog_last_counter = 1000; counter = 6000; rstc = 0;
    rpi5_watchdog_service_unlocked(true);
    assert(rpi5_wdog_deadline == 0 && !rpi5_wdog_terminal_reported && writes == 35 && notices == 1);
    puts("READY_AFTER_REAL_RELOAD_ONCE_DEADLINE_UNCHANGED_PASS MMIO_CLOCK_DOUBLES");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'ready.c').write_text(preamble + defines + '\n' + source[start:end] + main)
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all', p / 'ready.c', '-o', p / 'ready'],
                check=True, capture_output=True)
            result = subprocess.run([p / 'ready'], check=True, capture_output=True)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(result.stdout, b'READY_AFTER_REAL_RELOAD_ONCE_DEADLINE_UNCHANGED_PASS MMIO_CLOCK_DOUBLES\n')


if __name__ == '__main__':
    unittest.main()
