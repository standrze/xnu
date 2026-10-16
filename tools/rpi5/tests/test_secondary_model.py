# SPDX-License-Identifier: BSD-2-Clause
"""Production dispatch control flow with explicit PSCI/counter substitutes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class SecondaryModelTests(unittest.TestCase):
    def test_dispatch_and_stop_conditions(self):
        source = (ROOT / "loader/rpi5/probe_main.c").read_text()
        body = source[source.index("static int start_secondaries("):source.index("static int psci_affinity_inventory(")]
        record = source[source.index("struct secondary_record {"):source.index("static void capture_features(")]
        replacements = {
            '__asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));': 'mpidr = self_model;',
            '__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));': 'frequency = frequency_model;',
            '__asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(begin));': 'begin = 0;',
            '__asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));': 'now = stalled ? 0 : ++clock_model;',
            '__asm__ volatile("yield" ::: "memory");': '++yields;',
            '__asm__ volatile("dsb sy" ::: "memory");': '(void)0;',
        }
        for original, replacement in replacements.items():
            self.assertIn(original, body)
            body = body.replace(original, replacement)
        self.assertNotIn("__asm__", body)
        harness = r'''
#include "fdt.h"
#include <assert.h>
#include <string.h>
#define POLL_BUDGET 4
static uint64_t self_model, frequency_model, clock_model;
static unsigned mode, calls, queries, yields, stalled;
static uint64_t targets[4], slots[4];
static char output[4096];
static int text(const char *s) { strcat(output,s); return 1; }
static int hex(uint64_t v) { (void)v; return 1; }
static void probe_secondary_entry(void) {}
/* Deliberately non-index-ordered CPU-interface mapping. */
static uint32_t target_bit(uint64_t affinity) {
    const uint32_t map[4]={8,1,4,2}; return map[(affinity>>8)&3];
}
static uint32_t gic_target_mask(void) { return target_bit(self_model); }
'''
        mocks = r'''
static uint64_t rpi5_psci_query(uint64_t fid, uint64_t target) {
    assert(fid == 0xc4000004u); assert(target != (self_model & 0xff00ffffffull));
    queries++;
    if (calls && target==targets[calls-1]) {
        if (mode==19) return 0;
        if (mode==20) return 2;
        if (mode==21) return UINT64_MAX;
    }
    return mode == 1 ? 0 : mode == 2 ? 2 : 1;
}
static uint64_t rpi5_psci_cpu_on(uint64_t target, uintptr_t entry, uint64_t slot) {
    assert(entry == (uintptr_t)probe_secondary_entry && slot < 4 && calls < 4);
    targets[calls]=target; slots[calls++]=slot;
    if (mode == 3) return UINT64_MAX;
    if (mode == 4) return 0;
    probe_secondary_records[slot] = (struct secondary_record){
        target,4,0x30d00800,0x3c0,frequency_model,100,1,1,27,1,5,0,0,0,0,0,0,target_bit(target),{0}};
    for (unsigned f=0;f<9;f++) probe_secondary_records[slot].features[f]=primary_features[f];
    switch (mode) {
        case 5: probe_secondary_records[slot].mpidr ^= 0x100; break;
        case 6: probe_secondary_records[slot].el = 8; break;
        case 7: probe_secondary_records[slot].sctlr |= 1; break;
        case 8: probe_secondary_records[slot].daif = 0; break;
        case 9: probe_secondary_records[slot].frequency++; break;
        case 10: probe_secondary_records[slot].ready = 2; break;
        case 11: probe_secondary_records[slot].irq_verified = 0; break;
        case 12: probe_secondary_records[slot].irq_ack = 40; break;
        case 13: probe_secondary_records[slot].irq_count = 2; break;
        case 14: probe_secondary_records[slot].irq_timer_status = 7; break;
        case 15: probe_secondary_records[slot].gic_target = 0; break;
        case 16: probe_secondary_records[slot].gic_target = 3; break;
        case 17: probe_secondary_records[slot].gic_target = gic_target_mask(); break;
        case 18: probe_secondary_records[slot].features[8] ^= 1; break;
    }
    return 0;
}
static void reset(void) {
    memset((void *)probe_secondary_records,0,sizeof probe_secondary_records);
    calls=queries=yields=stalled=mode=0; clock_model=0; frequency_model=10;
    self_model=0x80000000; output[0]=0;
    for (unsigned f=0;f<9;f++) primary_features[f]=f+1;
}
'''
        cases = r'''
int main(void) {
    struct rpi5_fdt_cpus cpus={{0,256,512,768},4,15};
    reset(); assert(start_secondaries(&cpus)); assert(calls==3 && queries==6);
    for (unsigned i=0;i<3;i++) assert(targets[i]==(i+1)*256 && slots[i]==i+1);
    for (unsigned i=1;i<=21;i++) {
        reset(); mode=i; assert(!start_secondaries(&cpus));
        assert(calls==(i<=2 ? 0u : 1u)); /* No starts after the first failure. */
        if (i==10) assert(strstr(output,"SECONDARY_FAULT"));
    }
    reset(); mode=4; stalled=1; assert(!start_secondaries(&cpus));
    assert(calls==1 && yields==10*POLL_BUDGET && strstr(output,"TIMEOUT_NO_RETRY"));
    reset(); mode=19; stalled=1; assert(!start_secondaries(&cpus));
    assert(calls==1 && yields==10*POLL_BUDGET && strstr(output,"STOP_NOT_OFF"));
    reset(); probe_secondary_records[1].ready=1; assert(!start_secondaries(&cpus)); assert(!calls && !queries);
    reset(); self_model=0x80000400; assert(!start_secondaries(&cpus)); assert(!calls);
    reset(); frequency_model=0; assert(!start_secondaries(&cpus)); assert(!calls);
    reset(); cpus.enabled_mask=5; assert(start_secondaries(&cpus)); assert(calls==1 && targets[0]==512 && slots[0]==2);
    reset(); cpus.enabled_mask=14; assert(!start_secondaries(&cpus)); assert(!calls);
    reset(); cpus.enabled_mask=15; self_model=0x80000200; assert(start_secondaries(&cpus));
    assert(calls==3 && targets[0]==0 && slots[0]==0 && targets[1]==256 && targets[2]==768);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness + record + mocks + body + cases)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(ROOT / "loader/rpi5"), str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
