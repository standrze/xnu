# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RuntimeTimerFlowTests(unittest.TestCase):
    def test_poll_outcomes_and_cleanup(self):
        source=(ROOT/'loader/rpi5/probe_main.c').read_text()
        function='static int timer_probe(' + source.split('static int timer_probe(',1)[1].split(
            '\nstatic int owns_console(',1)[0]
        # Substitute only register accesses; execute the actual branching,
        # deadline arithmetic, bounded loop and result propagation on the host.
        replacements=iter([
            'frequency=model_frequency;',
            'model_control=2;',
            'begin=model_begin;',
            'model_deadline=deadline;',
            'model_control=3;',
            'control=model_status; now=model_now; ++reads;',
            'model_control=2;',
        ])
        function,count=re.subn(r'__asm__ volatile\(.*?\);',
            lambda match: next(replacements),function,flags=re.S)
        self.assertEqual(count,7)
        self.assertIn('if (!timer_probe()) return;',source)
        code=r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#define POLL_BUDGET 8
static uint64_t model_frequency,model_begin,model_now,model_status;
static uint64_t model_control,model_deadline;
static unsigned reads;
static int console_ok;
static int text(const char *s) { (void)s; return console_ok; }
static int hex(uint64_t x) { (void)x; return console_ok; }
''' + function + r'''
int main(void) {
    for (console_ok=0;console_ok<2;console_ok++) {
        model_frequency=1000; model_begin=100; model_now=101; model_status=7;
        reads=0; assert(timer_probe()==console_ok);
        assert(model_control==2 && model_deadline==101 && reads==1);
        model_status=0; reads=0;
        assert(timer_probe()==0 && reads==POLL_BUDGET && model_control==2);
        model_status=7; model_now=100;
        assert(timer_probe()==0 && model_control==2);
        model_now=99;
        assert(timer_probe()==0 && model_control==2);
        model_status=5; model_now=101;
        assert(timer_probe()==0 && model_control==2);
        model_begin=UINT64_MAX;
        assert(timer_probe()==0 && model_control==2);
        model_frequency=0; reads=0;
        assert(timer_probe()==0 && reads==0);
        model_frequency=(uint64_t)UINT32_MAX+1;
        assert(timer_probe()==0 && reads==0);
    }
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined',str(p/'test.c'),
                            '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
