# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]

class WatchdogBudgetTests(unittest.TestCase):
    def test_probe_budget_ignores_container_record_hash(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        observer = source.split('void rpi5_hash_progress(', 1)[1].split(
            'static int embedded_payload_inventory(', 1)[0]
        self.assertIn('total >= (1u<<20)', observer)
        self.assertIn('!hash_watchdog_budget.total && !completed', observer)
        self.assertIn('rpi5_watchdog_budget_step(&hash_watchdog_budget,counter,completed,total)', observer)

    def test_progress_deadline_and_finite_renewals(self):
        source = r'''
#include "watchdog_budget.h"
#include <assert.h>
#include <string.h>
int main(void) {
    struct rpi5_watchdog_budget b={100,10,1024,0,3}, old;
#define REJECT(now,done,total) do { old=b; \
    assert(!rpi5_watchdog_budget_step(&b,now,done,total)); \
    assert(!memcmp(&b,&old,sizeof b)); } while(0)
    assert(!rpi5_watchdog_budget_step(0,11,1,1024));
    REJECT(11,0,1024); REJECT(9,256,1024);
    REJECT(11,256,0); REJECT(11,256,2048); REJECT(11,1025,1024);
    REJECT(100,256,1024); REJECT(UINT64_MAX,256,1024);
    assert(rpi5_watchdog_budget_step(&b,11,256,1024));
    REJECT(12,256,1024); REJECT(12,128,1024);
    assert(rpi5_watchdog_budget_step(&b,11,512,1024));
    assert(rpi5_watchdog_budget_step(&b,11,768,1024));
    REJECT(11,1024,1024); /* stalled clock cannot renew forever */
    b=(struct rpi5_watchdog_budget){100,10,1024,0,8};
    assert(rpi5_watchdog_budget_step(&b,99,1024,1024));
    REJECT(99,1024,1024);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
