# SPDX-License-Identifier: BSD-2-Clause
"""Execute production IRQ-test control flow with explicit hardware substitutes.

Does not emulate exception entry, MMIO ordering, GIC security or timer timing.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class IRQModelTests(unittest.TestCase):
    def test_acknowledgment_handler(self):
        source = (ROOT / "loader/rpi5/probe_main.c").read_text()
        body = source[source.index("void probe_irq_handler(void)"):source.index("static void gic_inventory(void)")]
        substitutions = {
            '__asm__ volatile("mrs %0, cntv_ctl_el0" : "=r"(control));': 'control = timer; event(1);',
            '__asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)2) : "memory");': 'timer = 2; event(2);',
            '__asm__ volatile("dsb sy" ::: "memory");': 'event(3);',
        }
        for original, replacement in substitutions.items():
            self.assertIn(original, body)
            body = body.replace(original, replacement)
        self.assertNotIn("__asm__", body)
        harness = r'''
#include <stdint.h>
#include <assert.h>
#include <string.h>
static uint32_t probe_irq_count, probe_irq_last_ack, probe_irq_timer_status;
static uint32_t ack, ctl, timer, events[16], count, eoi, deactivate;
static void event(unsigned value) { assert(count < 16); events[count++] = value; }
static uint32_t read32(uintptr_t address) {
    if (address == 0x107fffa00cull) { event(0); return ack; }
    assert(address == 0x107fffa000ull); event(5); return ctl;
}
static void write32(uintptr_t address, uint32_t value) {
    assert(value == ack); /* Preserve source CPU bits, not merely INTID. */
    if (address == 0x107fffa010ull) { event(4); eoi++; }
    else { assert(address == 0x107fffb000ull); event(6); deactivate++; }
}
static void reset(uint32_t id, uint32_t mode) {
    ack = id; ctl = mode; timer = 5; count = eoi = deactivate = 0;
    probe_irq_count = probe_irq_last_ack = probe_irq_timer_status = 0;
}
'''
        cases = r'''
int main(void) {
    reset(27,0); probe_irq_handler();
    const uint32_t combined[] = {0,1,2,3,4,5,3};
    assert(count == 7 && !memcmp(events,combined,sizeof combined));
    assert(probe_irq_count == 1 && probe_irq_timer_status == 5 && timer == 2);
    assert(eoi == 1 && !deactivate);
    reset(27,1u<<9); probe_irq_handler();
    const uint32_t split[] = {0,1,2,3,4,5,6,3};
    assert(count == 8 && !memcmp(events,split,sizeof split));
    assert(eoi == 1 && deactivate == 1);
    reset(27,1u<<10); probe_irq_handler(); assert(eoi == 1 && !deactivate);
    reset(0x1401,1u<<9); probe_irq_handler();
    assert(probe_irq_last_ack == 0x1401 && !probe_irq_count && timer == 5);
    assert(eoi == 1 && deactivate == 1);
    for (unsigned id=1020; id<=1023; ++id) {
        reset(id,1u<<9); probe_irq_handler();
        assert(count == 1 && !eoi && !deactivate && !probe_irq_count && timer == 5);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness + body + cases)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)

    def test_setup_outcomes_and_cleanup(self):
        source = (ROOT / "loader/rpi5/probe_main.c").read_text()
        body = source[source.index("static void timer_irq_probe(void)\n{"):source.index("/* Bounded iteration count")]
        substitutions = {
            "mrs %0, cntfrq_el0; mrs %1, daif": "frequency = frequency_model; daif = daif_model;",
            "isb; mrs %0, cntvct_el0": "now = counter_model;",
            "msr cntv_cval_el0, %0; isb": "compare_model = deadline;",
            "msr cntv_ctl_el0, %0; isb": "timer_model = 1;",
            "msr daifclr, #2; isb": "unmask();",
            "msr daifset, #2; isb": "daif_model |= 0x80;",
            "msr cntv_ctl_el0, %0; isb; dsb sy": "timer_model = 2;",
            "yield": "++polls_model;",
            "dsb sy; isb": "(void)0;",
            "dsb sy": "(void)0;",
        }
        seen = set()
        def replace(match):
            instruction = re.search(r'"([^"]+)"', match[0])[1]
            self.assertIn(instruction, substitutions, "new assembly needs an explicit model")
            seen.add(instruction)
            return substitutions[instruction]
        body = re.sub(r'__asm__ volatile\(.*?\);', replace, body, flags=re.S)
        self.assertEqual(seen, set(substitutions))
        body = body.replace("*(volatile uint8_t *)(d + 0x400 + 27)", "priority_model")
        self.assertNotIn("volatile uint8_t *", body)
        harness = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#define POLL_BUDGET 32
static uint32_t distributor[1024], cpuif[2048];
static uint32_t probe_irq_count, probe_irq_last_ack, probe_irq_timer_status;
static uint32_t probe_irq_verified;
static uint64_t frequency_model, counter_model, daif_model, compare_model;
static unsigned timer_model, polls_model, writes_model, unmask_model;
static unsigned event_model, deny_enable, deny_cleanup;
static uint8_t priority_model;
static char output[2048];
static int text(const char *s) { strcat(output, s); return 1; }
static int hex(uint64_t v) { (void)v; return 1; }
static uint32_t read32(uintptr_t a) {
    if (a >= 0x107fff9000ull && a < 0x107fffa000ull) return distributor[(a-0x107fff9000ull)/4];
    assert(a >= 0x107fffa000ull && a < 0x107fffc000ull);
    return cpuif[(a-0x107fffa000ull)/4];
}
static void write32(uintptr_t a, uint32_t v) {
    ++writes_model;
    if (a >= 0x107fff9000ull && a < 0x107fffa000ull) {
        unsigned off = (unsigned)(a-0x107fff9000ull);
        if (off == 0x100) { if (!deny_enable) distributor[0x100/4] |= v; }
        else if (off == 0x180) { if (!deny_cleanup) distributor[0x100/4] &= ~v; }
        else if (off == 0x280) distributor[0x200/4] &= ~v;
        else distributor[off/4] = v;
    } else {
        assert(a >= 0x107fffa000ull && a < 0x107fffc000ull);
        cpuif[(a-0x107fffa000ull)/4] = v;
    }
}
static void unmask(void) {
    ++unmask_model;
    assert(timer_model == 1 && compare_model > counter_model);
    assert(distributor[0x100/4] == (1u<<27));
    assert(distributor[0] & 1); assert(cpuif[0] & 1);
    daif_model &= ~0x80ull;
    if (event_model) {
        probe_irq_last_ack = event_model == 1 ? 27 : 40;
        probe_irq_count = event_model == 1;
        probe_irq_timer_status = event_model == 1 ? 5 : 0;
        daif_model |= 0x80; /* Model the assembly's one-shot return. */
    }
}
static void reset(void) {
    memset(distributor, 0, sizeof distributor); memset(cpuif, 0, sizeof cpuif);
    distributor[1] = (1u<<10) | 1; cpuif[0xfc/4] = 2u<<16;
    cpuif[0] = 0x260; cpuif[1] = 0xa0; priority_model = 0x60;
    frequency_model = 1000000; counter_model = 1000; daif_model = 0x3c0;
    timer_model = 2; polls_model = writes_model = unmask_model = 0;
    deny_enable = deny_cleanup = event_model = 0; output[0] = 0;
}
'''
        cases = r'''
int main(void) {
    reset(); event_model = 1; timer_irq_probe();
    assert(strstr(output, "SINGLE_CPU_IRQ_OBSERVED"));
    assert(unmask_model == 1 && timer_model == 2 && (daif_model & 0x80));
    assert(!distributor[0] && !distributor[0x100/4]);
    assert(cpuif[0] == 0x260 && cpuif[1] == 0xa0 && priority_model == 0x60);
    reset(); timer_irq_probe(); assert(polls_model == POLL_BUDGET);
    assert(strstr(output, "NOT_CONFIRMED") && timer_model == 2 && (daif_model & 0x80));
    reset(); event_model = 2; timer_irq_probe(); assert(strstr(output, "NOT_CONFIRMED"));
    reset(); deny_enable = 1; timer_irq_probe(); assert(!unmask_model && strstr(output, "NOT_CONFIRMED"));
    reset(); event_model = 1; deny_cleanup = 1; timer_irq_probe(); assert(strstr(output, "NOT_CONFIRMED"));
    reset(); counter_model = UINT64_MAX; timer_irq_probe(); assert(!unmask_model && timer_model == 2);
    reset(); frequency_model = 0; timer_irq_probe(); assert(!writes_model && !unmask_model);
    reset(); distributor[0x104/4] = 1; timer_irq_probe(); assert(!writes_model && !unmask_model);
    reset(); distributor[0x200/4] = 1; timer_irq_probe(); assert(!writes_model && !unmask_model);
    reset(); distributor[0x300/4] = 1; timer_irq_probe(); assert(!writes_model && !unmask_model);
    reset(); distributor[0xc04/4] = 1u<<23; timer_irq_probe(); assert(!writes_model && !unmask_model);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness + body + cases)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
