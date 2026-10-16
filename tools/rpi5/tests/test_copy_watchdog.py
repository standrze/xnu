from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class CopyWatchdogTests(unittest.TestCase):
    def test_checkpoint_limits(self):
        source=(ROOT/'loader/rpi5/probe_main.c').read_text()
        body='static void copy_watchdog_checkpoint('+source.split(
            'static void copy_watchdog_checkpoint(',1)[1].split('\nstatic int payload_stage(',1)[0]
        body=body.replace('__asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));','now=clock_model;')
        body=body.replace('__asm__ volatile("dsb sy" ::: "memory");','(void)0;')
        self.assertNotIn('__asm__',body)
        code=r'''
#include "watchdog_budget.h"
#include <assert.h>
static uintptr_t copy_watchdog_base;
static struct rpi5_watchdog_budget copy_watchdog_budget;
static uint64_t clock_model;
static unsigned writes, control;
static uint32_t read32(uintptr_t p) { assert(p==0x101c); return control; }
static void write32(uintptr_t p,uint32_t v) {
    assert(p==0x1024 && v==(0x5a000000u|(15u<<16))); ++writes;
}
static void reset(void) {
    copy_watchdog_base=0x1000;
    copy_watchdog_budget=(struct rpi5_watchdog_budget){60,0,2,0,2};
    clock_model=10; writes=0; control=0x20;
}
'''+body+r'''
int main(void) {
    reset(); copy_watchdog_checkpoint(1); assert(writes==1);
    copy_watchdog_checkpoint(1); assert(writes==1);
    copy_watchdog_checkpoint(2); assert(writes==2 && !copy_watchdog_base);
    copy_watchdog_checkpoint(2); assert(writes==2);
    reset(); copy_watchdog_checkpoint(2); assert(!writes && !copy_watchdog_base);
    reset(); clock_model=60; copy_watchdog_checkpoint(1); assert(!writes);
    reset(); copy_watchdog_checkpoint(1); clock_model=9;
    copy_watchdog_checkpoint(2); assert(writes==1);
    reset(); control=0; copy_watchdog_checkpoint(1); assert(!writes);
    reset(); copy_watchdog_base=0; copy_watchdog_checkpoint(1); assert(!writes);
    reset(); clock_model=0; copy_watchdog_checkpoint(1); copy_watchdog_checkpoint(2);
    for(unsigned i=0;i<100;i++) copy_watchdog_checkpoint(2);
    assert(writes==2);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
