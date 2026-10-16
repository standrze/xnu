# SPDX-License-Identifier: BSD-2-Clause
"""Exercise the Pi kernel GICv2 source against a small MMIO model."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "pexpert/arm/pe_fiq.c"


def pi_function(source: str, name: str) -> str:
    match = re.search(r"\n(?:void|bool|uint32_t|static uint32_t|static void)\n" +
                      name + r"\([^)]*\)\n\{", source)
    if match is None:
        raise AssertionError(f"missing Pi GIC function {name}")
    opening = source.index("{", match.start())
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start() + 1:end]


class KernelGICTests(unittest.TestCase):
    def test_irq_dispatch_orders_timer_service_before_eoi(self):
        source = (ROOT / "osfmk/arm64/sleh.c").read_text()
        dispatch = source.split("sleh_irq(arm_saved_state_t *state)\n{", 1)[1].split(
            "\nvoid\nsleh_fiq(", 1)[0]
        pi = dispatch.split("#if defined(ARM64_BOARD_CONFIG_BCM2712)", 2)[-1].split(
            "#elif USE_APPLEARMSMP", 1)[0]
        self.assertLess(pi.index("pe_rpi5_irq_acknowledge()"),
                        pi.index("ml_get_timer_pending()"))
        self.assertLess(pi.index("rtclock_intr(TRUE)"),
                        pi.index("pe_rpi5_irq_complete(rpi5_iar)"))
        self.assertIn('panic("BCM2712: unexpected IRQ', pi)

    def test_pi_gic_init_and_completion(self):
        source = SOURCE.read_text().split("#elif defined(ARM64_BOARD_CONFIG_BCM2712)", 1)[1].split("#else", 1)[0]
        definitions = source.split("static vm_offset_t rpi5_gicd_base;", 1)[0]
        functions = "\n\n".join(pi_function(source, name) for name in
                                ("rpi5_mmio_read32", "rpi5_mmio_write32",
                                 "rpi5_init_local_gic", "pe_init_fiq",
                                 "pe_rpi5_irq_acknowledge", "pe_rpi5_irq_complete",
                                 "pe_rpi5_watchdog_enable_soak",
                                 "pe_rpi5_watchdog_enable_terminal"))
        functions += "\n\n" + pi_function(source, "pe_rpi5_watchdog_timer_tick")
        model = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define DSB_SY 0
#define ISB_SY 0
#define __builtin_arm_dsb(x) (++barriers)
#define __builtin_arm_isb(x) (++barriers)
#define kSuccess 0
typedef uintptr_t vm_offset_t;
typedef void *DTEntry;
static uint32_t distributor[0x1000 / 4], cpuif[0x2000 / 4];
static uint64_t reg[4] = {0x3ff9000, 0x1000, 0x3ffa000, 0x2000};
static uint32_t pm[0x4000 / 4];
static uint64_t watchdog_reg[2] = {0x1200000, 0x308};
static uint64_t timer_counter = 100;
#define __builtin_arm_rsr64(name) (strcmp(name, "CNTFRQ_EL0") == 0 ? 54000000ULL : timer_counter)
static unsigned barriers, maps, error;
static jmp_buf fault;
static int SecureDTLookupEntry(void *root, const char *path, DTEntry *entry) {
    assert(root == 0);
    if (strcmp(path, "/arm-io/watchdog") == 0) { *entry = (void *)2; return kSuccess; }
    assert(strcmp(path, "/arm-io/gic") == 0);
    if (error == 1) return 1;
    *entry = (void *)1; return kSuccess;
}
static int SecureDTGetProperty(DTEntry entry, const char *name,
                               const void **value, unsigned *size) {
    if (entry == (void *)2) {
        if (strcmp(name, "compatible") == 0) {
            *value = "brcm,bcm2712-pm"; *size = sizeof("brcm,bcm2712-pm"); return kSuccess;
        }
        assert(strcmp(name, "reg") == 0);
        *value = watchdog_reg; *size = sizeof(watchdog_reg); return kSuccess;
    }
    assert(entry && strcmp(name, "reg") == 0);
    if (error == 2) return 1;
    *value = reg; *size = error == 3 ? 8 : sizeof(reg); return kSuccess;
}
static vm_offset_t pe_arm_get_soc_base_phys(void) { return 0x107c000000ULL; }
static vm_offset_t ml_io_map(uint64_t base, uint64_t size) {
    maps++;
    if (base == 0x107fff9000ULL && size == 0x1000) return (vm_offset_t)distributor;
    if (base == 0x107fffa000ULL && size == 0x2000) return (vm_offset_t)cpuif;
    if (base == 0x107d200000ULL && size == 0x4000) return (vm_offset_t)pm;
    assert(0); return 0;
}
static __attribute__((noreturn)) void panic(const char *message, ...) {
    (void)message; longjmp(fault, 1);
}
static void kprintf(const char *message, ...) { (void)message; }
''' + definitions + r'''
static vm_offset_t rpi5_gicd_base;
static vm_offset_t rpi5_gicc_base;
static vm_offset_t rpi5_pm_base;
static uint64_t rpi5_wdog_deadline, rpi5_wdog_last_counter, rpi5_wdog_reload_ticks;
static unsigned rpi5_wdog_reloads;
static uint32_t rpi5_wdog_soak_seconds;
static bool rpi5_wdog_terminal_enabled;
static uint64_t rpi5_wdog_soak_start_counter, rpi5_wdog_soak_grace_ticks;
''' + functions + r'''
static void reset(void) {
    memset(distributor, 0, sizeof(distributor)); memset(cpuif, 0, sizeof(cpuif));
    memset(pm, 0, sizeof(pm));
    rpi5_gicd_base = rpi5_gicc_base = rpi5_pm_base = 0;
    rpi5_wdog_deadline = rpi5_wdog_last_counter = rpi5_wdog_reload_ticks = 0;
    rpi5_wdog_reloads = 0; timer_counter = 100;
    rpi5_wdog_soak_seconds = 0;
    rpi5_wdog_terminal_enabled = false;
    rpi5_wdog_soak_start_counter = rpi5_wdog_soak_grace_ticks = 0;
    reg[0] = 0x3ff9000; error = maps = barriers = 0;
    /* Non-secure board readback returned zero although PPI27 delivered. */
    distributor[0x80 / 4] = 0;
    distributor[(0x400 + 24) / 4] = 0x12345678;
    cpuif[0] = 1U << 9;
    pm[0x1c / 4] = 0x20;
}
int main(void) {
    reset(); pe_init_fiq();
    assert(maps == 3 && barriers == 2);
    assert(distributor[0x100 / 4] == (1U << 27));
    assert(distributor[0] == 1 && cpuif[0] == 1 && cpuif[4 / 4] == 0xff);
    assert(distributor[(0x400 + 24) / 4] == 0x80345678);
    cpuif[0xc / 4] = 0x400 | 27;
    assert(pe_rpi5_irq_acknowledge() == (0x400 | 27));
    pe_rpi5_irq_complete(0x400 | 27);
    assert(cpuif[0x10 / 4] == (0x400 | 27) && barriers == 4);
    timer_counter += 5ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(pm[0x24 / 4] == (0x5a000000U | (15U << 16)));
    assert(rpi5_wdog_reloads == 1);
    pm[0x24 / 4] = 0;
    pe_rpi5_watchdog_timer_tick(true);
    assert(pm[0x24 / 4] == 0 && rpi5_wdog_reloads == 1);
    rpi5_wdog_reloads = 24;
    timer_counter += 5ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(pm[0x24 / 4] == 0 && rpi5_wdog_reloads == 24);
    rpi5_wdog_reloads = 1;
    timer_counter += 120ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(rpi5_wdog_reloads == 1);
    reset(); pe_init_fiq();
    assert(pe_rpi5_watchdog_enable_terminal());
    assert(!pe_rpi5_watchdog_enable_terminal());
    assert(!pe_rpi5_watchdog_enable_soak(300));
    for (unsigned i = 0; i < 25; i++) {
        timer_counter += 5ULL * 54000000;
        pe_rpi5_watchdog_timer_tick(true);
    }
    assert(rpi5_wdog_reloads == 25);
    assert(rpi5_wdog_deadline == 100 + 3600ULL * 54000000);
    timer_counter = rpi5_wdog_deadline;
    pe_rpi5_watchdog_timer_tick(true);
    assert(rpi5_wdog_reloads == 25);
    reset(); pe_init_fiq();
    pm[0x1c / 4] = 0;
    timer_counter += 5ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(rpi5_wdog_reloads == 0 && rpi5_wdog_deadline == 0);
    reset(); pe_init_fiq();
    assert(pe_rpi5_watchdog_enable_soak(300));
    timer_counter += 5ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(false);
    assert(rpi5_wdog_reloads == 0);
    timer_counter += 5ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(rpi5_wdog_reloads == 1);
    for (unsigned i = 0; i < 25; i++) {
        timer_counter += 5ULL * 54000000;
        pe_rpi5_watchdog_timer_tick(true);
    }
    assert(rpi5_wdog_reloads == 26);
    timer_counter = rpi5_wdog_soak_start_counter + 300ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(true);
    assert(rpi5_wdog_deadline == 0);
    reset(); pe_init_fiq();
    assert(!pe_rpi5_watchdog_enable_soak(59));
    assert(!pe_rpi5_watchdog_enable_soak(28801));
    assert(pe_rpi5_watchdog_enable_soak(300));
    timer_counter = rpi5_wdog_soak_start_counter + 300ULL * 54000000;
    pe_rpi5_watchdog_timer_tick(false);
    assert(rpi5_wdog_deadline == 0 && rpi5_wdog_reloads == 0);
    reset(); pe_init_fiq();
    /* A second CPU reuses shared mappings but must program banked GICC/PPI. */
    cpuif[0] = 1U << 9;
    cpuif[4 / 4] = 0;
    distributor[(0x400 + 24) / 4] = 0x12345678;
    unsigned prior_barriers = barriers;
    pe_init_fiq();
    assert(maps == 3 && barriers == prior_barriers + 2);
    assert(cpuif[0] == 1 && cpuif[4 / 4] == 0xff);
    assert(distributor[(0x400 + 24) / 4] == 0x80345678);
    reset(); distributor[0x100 / 4] = 1U << 28;
    if (!setjmp(fault)) { pe_init_fiq(); assert(0); }
    reset(); error = 3;
    if (!setjmp(fault)) { pe_init_fiq(); assert(0); }
    reset(); reg[0]++;
    if (!setjmp(fault)) { pe_init_fiq(); assert(0); }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            executable = path / "gic-model"
            result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                                     "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                     "-xc", "-", "-o", str(executable)], input=model,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
