#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exercise the exact frozen service body with explicitly fake MMIO/time only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'build/rpi5/root42-confirmed-kernel-20261013-final'
MANIFEST = 'a51d2a68adb182b2980c67da3288f562d90727ef2a677fb8aa27890a6aca4539'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[opening:cursor]


class ConfirmationService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert sha(PACKAGE / 'manifest.json') == MANIFEST
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())
        for name, expected in cls.report['generated_sha256'].items():
            assert sha(Path(name)) == expected, name
        cls.source = (PACKAGE / 'pe_fiq.c').read_text()
        cls.service = body(cls.source, 'rpi5_watchdog_service_unlocked(bool healthy)')

    def test_actual_arm64_atomic_and_gate_lowering(self):
        mount = (PACKAGE / 'mockfs_vfsops.s').read_text()
        getter = mount.split('_mockfs_rpi5_root_snapshot:', 1)[1].split('; -- End function', 1)[0]
        self.assertRegex(getter, r'\tldapr\tx9, \[x9\]')
        self.assertNotIn('\tbl\t', getter)
        self.assertTrue(re.search(r'_mockfs_rpi5_confirmed_root@PAGEOFF\n\tstlr\tx8, \[x9\]', mount))
        revoke = mount.split('_mockfs_unmount:', 1)[1].split('; -- End function', 1)[0]
        self.assertIn('_mockfs_rpi5_confirmed_root@PAGE', revoke)
        self.assertIn('\tstlr\txzr, [x8]', revoke)
        pe = (PACKAGE / 'pe_fiq.s').read_text()
        tick = pe.split('_pe_rpi5_watchdog_timer_tick:', 1)[1].split('; -- End function', 1)[0]
        self.assertLess(tick.index('\tcasa\t'), tick.index('\tbl\t_mockfs_rpi5_root_snapshot'))
        self.assertIn('\tstlr\twzr, [x19]', tick)
        self.assertTrue('\tcmp\tw8, #2' in tick)
        self.assertIn('\tbl\t_kprintf', tick)
        # Exact unchanged owner wrapper acquires before service and releases after it.
        owner = ROOT / 'pexpert/arm/rpi5_pcie_watchdog_owner.inc'
        self.assertEqual(sha(owner), self.report['inputs_sha256'][str(owner)])
        wrapper = body(owner.read_text(), 'pe_rpi5_watchdog_timer_tick(bool healthy)')
        self.assertLess(wrapper.index('rpi5_pcie_watchdog_gate_service'), wrapper.index('rpi5_watchdog_service_unlocked'))
        self.assertLess(wrapper.index('rpi5_watchdog_service_unlocked'), wrapper.index('rpi5_pcie_watchdog_gate_leave'))

    def test_original_service_timing_and_mount_publication(self):
        # We execute the *actual* service body, not a reimplemented state machine.
        # Only the hardware clock/MMIO/barrier and output endpoints are doubles.
        declarations = self.source.split('static vm_offset_t rpi5_gicd_base;', 1)[1].split('static uint32_t\nrpi5_mmio_read32', 1)[0]
        declarations = declarations.replace('static vm_offset_t rpi5_gicc_base;\n', '')
        defines = '\n'.join(line for line in self.source.splitlines()
                            if re.match(r'#define RPI5_(?:PM_(?:RSTC|WDOG|FULL_RESET)|WDOG_(?:PASSWORD|INTERVAL|MAX_RELOADS)|TERMINAL_WDOG_SECONDS)\b', line))
        owner = ROOT / 'pexpert/arm/rpi5_pcie_watchdog_owner.inc'
        wrapper = body(owner.read_text(), 'pe_rpi5_watchdog_timer_tick(bool healthy)')
        source = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#include "HEADER"
#include "GATE"
DEFINES
DECLARATIONS
static uint64_t fake_now, published;
static uint32_t fake_route;
static unsigned writes, barriers, notices, roots;
static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;
#define DSB_SY 0
#define __builtin_arm_rsr64(name) fake_now
#define __builtin_arm_dsb(scope) ((void)(scope), ++barriers)
static uint32_t rpi5_mmio_read32(vm_offset_t base, unsigned offset) {
    assert(base == 1 && offset == RPI5_PM_RSTC); return fake_route;
}
static void rpi5_mmio_write32(vm_offset_t base, unsigned offset, uint32_t value) {
    assert(base == 1 && offset == RPI5_PM_WDOG);
    assert(value == (RPI5_WDOG_PASSWORD | RPI5_WDOG_INTERVAL)); ++writes;
}
bool mockfs_rpi5_root_snapshot(uint32_t *nodes, uint64_t *bytes) {
    return rpi5_root_confirmation_snapshot(&published, nodes, bytes);
}
static void kprintf(const char *format, ...) {
    assert(writes && barriers == writes);
    if (strstr(format, ":ROOT_READY ")) ++roots;
    if (strstr(format, ":WATCHDOG_READY ")) ++notices;
}
static void rpi5_watchdog_service_unlocked(bool healthy) SERVICE
static void pe_rpi5_watchdog_timer_tick(bool healthy) WRAPPER
static void reset(void) {
    rpi5_pm_base=1; rpi5_wdog_deadline=190; rpi5_wdog_last_counter=10;
    rpi5_wdog_reload_ticks=5; rpi5_wdog_reloads=0; rpi5_wdog_soak_seconds=0;
    rpi5_wdog_terminal_enabled=true; rpi5_wdog_terminal_reported=false;
    rpi5_wdog_terminal_report_after=15; rpi5_wdog_root_reports=0;
    fake_now=10; fake_route=RPI5_PM_FULL_RESET; published=0;
    writes=barriers=notices=roots=0; memset(&rpi5_pcie_wdog_gate, 0, sizeof(rpi5_pcie_wdog_gate));
}
static void tick(uint64_t now) { fake_now=now; pe_rpi5_watchdog_timer_tick(true); }
int main(void) {
    reset(); tick(14); assert(!roots && !writes); /* before reload/notice threshold */
    tick(15); assert(notices==1 && roots==0 && rpi5_wdog_root_reports==0);
    tick(20); assert(notices==1 && roots==0 && rpi5_wdog_root_reports==0);
    assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    tick(24); assert(!roots); tick(25); assert(roots==1 && notices==1);
    tick(30); tick(35); tick(40); assert(roots==3 && rpi5_wdog_root_reports==3);
    assert(rpi5_wdog_deadline==190); tick(190); assert(writes==6 && roots==3);
    reset(); assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    rpi5_wdog_terminal_report_after=25; tick(15); assert(writes==1 && roots==0 && notices==0);
    tick(20); assert(roots==0); tick(25); assert(roots==1 && notices==1);
    rpi5_root_confirmation_clear(&published); tick(30); assert(roots==1);
    assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    tick(35); assert(roots==2 && rpi5_wdog_deadline==190);
    reset(); assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    fake_route=0; tick(15); assert(writes==0 && roots==0 && rpi5_wdog_deadline==0);
    reset(); assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    rpi5_pcie_wdog_gate.busy=1; tick(15); assert(writes==0 && roots==0);
    rpi5_pcie_wdog_gate.busy=0; rpi5_pcie_wdog_gate.owner=&published;
    tick(15); assert(writes==0 && roots==0 && rpi5_wdog_deadline==190);
    reset(); assert(rpi5_root_confirmation_publish(&published,42,2506752,true));
    rpi5_wdog_terminal_report_after=0; tick(15); assert(writes==1 && roots==0 && notices==0);
    puts("ROOT_CONFIRMATION_SERVICE PASS DELAYED_MOUNT ABSENT_MOUNT FAILED_ROUTE BEFORE_THRESHOLD MAX3 REVOKED BUSY OWNED DEADLINE_UNCHANGED");
    return 0;
}
'''.replace('HEADER', str(ROOT / 'loader/rpi5/ramroot_confirmation.h'))
        source = source.replace('GATE', str(ROOT / 'loader/rpi5/pcie_watchdog_gate.h'))
        source = source.replace('DEFINES', defines).replace('DECLARATIONS', declarations)
        source = source.replace('SERVICE', self.service, 1).replace('WRAPPER', wrapper, 1)
        with tempfile.TemporaryDirectory(prefix='root-confirmation-service-') as directory:
            path = Path(directory) / 'actual_service.c'
            path.write_text(source)
            binary = path.with_suffix('')
            compilation = subprocess.run(['xcrun', 'clang', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined',
                            '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)],
                           capture_output=True, text=True)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ROOT_CONFIRMATION_SERVICE PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
