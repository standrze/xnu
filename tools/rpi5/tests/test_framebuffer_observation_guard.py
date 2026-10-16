# SPDX-License-Identifier: BSD-2-Clause
"""Actual arm/byte functions with explicit host MMIO/clock/UART doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'loader/rpi5/probe_framebuffer_observe_main.c'
class FramebufferObservationGuardTests(unittest.TestCase):
    def test_actual_bounded_arm_and_output_failures(self):
        source=SOURCE.read_text();body=source[source.index('static int within('):source.index('void probe_main(')]
        old='*(volatile uint32_t *)(PM+0x24)=UINT32_C(0x5a0f0000);__asm__ volatile("dsb sy" ::: "memory");'
        self.assertEqual(body.count(old),1);body=body.replace(old,'write_countdown(UINT32_C(0x5a0f0000));')
        program=r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
#define PM UINT64_C(0x107d200000)
#define UART UINT64_C(0x107d001000)
#define UART_BUDGET 1000000u
#define OUTPUT_LIMIT 32768u
#define RPI5_UART_OK 0
static uint64_t frequency=1000000,deadline,ticks;
static unsigned armed,bytes_written,writes,reads,uart_calls;
static uint32_t route,prior,left;static int uart_failure;static uint64_t uart_cost;
static uint64_t counter(void){return ticks;}
static uint32_t rpi5_access_load32(uintptr_t p){reads++;assert(p==PM+0x1c || p==PM+0x24);return p==PM+0x1c?route:(writes?left:prior);}
static void write_countdown(uint32_t value){assert(value==0x5a0f0000);assert(!writes);writes++;}
static int rpi5_uart_putc(uintptr_t p,unsigned char c,unsigned budget){assert(p==UART && budget==UART_BUDGET);(void)c;uart_calls++;ticks+=uart_cost;return uart_failure;}
'''+body+r'''
static void reset(void){armed=bytes_written=writes=reads=uart_calls=0;frequency=1000000;ticks=100;route=0x20;prior=1;left=15u<<16;uart_failure=0;uart_cost=0;}
int main(void){
reset();assert(!arm() && writes==1 && armed && deadline==8000100);assert(hex(1));
for(unsigned i=0;i<7;i++){reset();switch(i){case 0:route=0;break;case 1:route=UINT32_MAX;break;case 2:prior=0;break;case 3:prior=UINT32_MAX;break;case 4:ticks=UINT64_MAX-1;break;case 5:left=0;break;case 6:left=UINT32_MAX;break;}assert(arm());assert(writes==(i>=5));}
reset();uart_failure=1;assert(arm() && writes==1 && uart_calls==1);
reset();uart_cost=8000000;assert(arm() && writes==1 && uart_calls==1);
reset();assert(!arm());ticks=deadline;unsigned priorcalls=uart_calls;assert(!byte('x') && uart_calls==priorcalls);
reset();assert(!arm());bytes_written=OUTPUT_LIMIT;priorcalls=uart_calls;assert(!text("x") && uart_calls==priorcalls);
puts("ACTUAL_GUARD PASS ACTIVE_ONLY=1 ONE_WRITE=1 NO_ROUTE_WRITE=1 BOUNDED_OUTPUT=1");return 0;}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'guard.c').write_text(program)
            r=subprocess.run(['xcrun','clang','-O1','-g','-fsanitize=address,undefined','-Wall','-Wextra','-Werror',p/'guard.c','-o',p/'guard'],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([p/'guard'],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertIn('ACTUAL_GUARD PASS',r.stdout)
if __name__=='__main__':unittest.main()
