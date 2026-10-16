# SPDX-License-Identifier: BSD-2-Clause
"""Execute the actual 180-second PE deadline/reload bodies with explicit MMIO/clock doubles."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import root_capacity_profile as profile

BASE = profile.ROOT / 'build/rpi5/root-capacity-rp1-kernel-20261013-bounded'


class BoundedWatchdogTests(unittest.TestCase):
    def test_real_deadline_and_reload_bodies(self):
        manifest = json.loads((BASE / 'manifest.json').read_text())
        source = (BASE / 'pe_fiq.c').read_text()
        self.assertEqual(profile.sha(source.encode()), manifest['modified_pe_source_sha256'])
        original = profile.ROOT / 'build/rpi5/pcie-fw-client-kernel-20261013-final/pe_fiq.c'
        self.assertEqual(source, original.read_text().replace('#define RPI5_TERMINAL_WDOG_SECONDS 3600U',
                                                            '#define RPI5_TERMINAL_WDOG_SECONDS 180U'))
        start = source.index('bool\npe_rpi5_watchdog_enable_terminal(void)')
        end = source.index('#if RPI5_PCI_WDOG_LEASE\n#include', start)
        defines = '\n'.join(line for line in source.splitlines() if line.startswith('#define RPI5_') and any(
            name in line.split()[1] for name in ('WDOG', 'PM_RSTC', 'PM_WDOG', 'PM_FULL_RESET')))
        preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define RPI5_PCI_WDOG_LEASE 1
#define DSB_SY 0
#define kprintf(...) ((void)0)
#define __builtin_arm_dsb(a) ((void)(a))
static uint64_t frequency, counter, rpi5_pm_base, rpi5_wdog_deadline;
static uint64_t rpi5_wdog_last_counter, rpi5_wdog_reload_ticks;
static uint64_t rpi5_wdog_soak_start_counter, rpi5_wdog_soak_grace_ticks;
static unsigned rpi5_wdog_reloads, rpi5_wdog_soak_seconds, writes;
static bool rpi5_wdog_terminal_enabled;
static uint64_t clock_read(const char *name) {
    assert(!strcmp(name,"CNTFRQ_EL0") || !strcmp(name,"CNTVCT_EL0"));
    return !strcmp(name,"CNTFRQ_EL0") ? frequency : counter;
}
#define __builtin_arm_rsr64(name) clock_read(name)
static uint32_t rpi5_mmio_read32(uint64_t base, unsigned offset) {
    assert(base == 1 && offset == 0x1c); return 0x20;
}
static void rpi5_mmio_write32(uint64_t base, unsigned offset, uint32_t value) {
    assert(base == 1 && offset == 0x24 && value == UINT32_C(0x5a0f0000)); writes++;
}
'''
        main = r'''
int main(void) {
    frequency = 1000; counter = 1000; rpi5_pm_base = 0; rpi5_wdog_deadline = 2000;
    assert(!pe_rpi5_watchdog_enable_terminal());
    rpi5_pm_base = 1; frequency = 0;
    assert(!pe_rpi5_watchdog_enable_terminal());
    frequency = UINT64_MAX;
    assert(!pe_rpi5_watchdog_enable_terminal());
    frequency = 1000; counter = UINT64_MAX - 179999;
    assert(!pe_rpi5_watchdog_enable_terminal());
    counter = 1000;
    assert(pe_rpi5_watchdog_enable_terminal());
    assert(rpi5_wdog_deadline == 181000 && writes == 0);
    assert(!pe_rpi5_watchdog_enable_terminal());
    assert(pe_rpi5_watchdog_terminal_active() && !pe_rpi5_watchdog_soak_active());
    rpi5_wdog_last_counter = counter; rpi5_wdog_reload_ticks = 5000;
    for (unsigned second = 5; second < 180; second += 5) {
        counter = 1000 + 1000 * second;
        rpi5_watchdog_service_unlocked(true);
        assert(writes == second / 5 && rpi5_wdog_last_counter == counter);
    }
    assert(writes == 35);
    counter = 181000;
    assert(!pe_rpi5_watchdog_terminal_active());
    rpi5_watchdog_service_unlocked(true);
    counter = 196000; rpi5_watchdog_service_unlocked(true);
    assert(writes == 35);
    puts("ACTUAL_TERMINAL_WATCHDOG_180S_STOP_RELOAD_PASS MMIO_CLOCK_DOUBLES");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            harness = out / 'deadline.c'
            harness.write_text(preamble + defines + '\n' + source[start:end] + main)
            binary = out / 'deadline'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            str(harness), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(result.stdout, b'ACTUAL_TERMINAL_WATCHDOG_180S_STOP_RELOAD_PASS MMIO_CLOCK_DOUBLES\n')


if __name__ == '__main__':
    unittest.main()
