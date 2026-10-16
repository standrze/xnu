# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RuntimeReservationFlowTests(unittest.TestCase):
    def test_validation_failure_is_not_console_success(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        function = source.split('static int runtime_reservations(', 1)[1]
        function = 'static int runtime_reservations(' + function.split('\nstatic int runtime_seed_metadata(', 1)[0]
        # Execute the actual runtime function with controlled parser/console
        # outcomes. This tests propagation, not MMIO or the parsers themselves.
        harness = r'''
#include "fdt.h"
#include <assert.h>
#include <string.h>
static const unsigned char __probe_start[1], __probe_end[1];
static int scenario, console_ok, resolved_calls;
static int text(const char *s) { (void)s; return console_ok; }
static int hex(uint64_t x) { (void)x; return console_ok; }
int rpi5_fdt_reservation_plan(const void *p,size_t n,struct rpi5_reservation_plan *o) {
    (void)p; (void)n; memset(o,0,sizeof *o);
    if (scenario==1) return -1;
    if (scenario==2) return -2;
    o->fixed.count=scenario==3 ? 32 : scenario==6 ? 31 : 0;
    return 0;
}
int rpi5_fdt_initrd(const void *p,size_t n,struct rpi5_range *o) {
    (void)p; (void)n; *o=(struct rpi5_range){0x900000,0x910000};
    return scenario==4 ? -1 : (scenario==5 || scenario==6) ? 0 : 1;
}
int rpi5_ranges_validate_live(const struct rpi5_range *r,size_t nr,
    const struct rpi5_range *l,size_t nl) {
    (void)r; (void)nr; (void)l; (void)nl; return scenario==5 || scenario==8 ? -1 : 0;
}
int rpi5_resolve_reservations(const struct rpi5_fdt_memory *m,
    const struct rpi5_reservation_plan *p,const struct rpi5_range *l,
    size_t n,struct rpi5_resolved_reservations *o) {
    (void)m; (void)p; (void)l; (void)n; ++resolved_calls;
    memset(o,0,sizeof *o); return scenario==7 ? -1 : 0;
}
'''
        harness += function + r'''
int main(void) {
    struct rpi5_fdt_memory memory={0}; memory.count=1;
    struct rpi5_resolved_reservations output, before;
    memset(&before,0xa5,sizeof before);
    for (console_ok=0; console_ok<=1; ++console_ok) {
        for (scenario=1; scenario<=8; ++scenario) {
            resolved_calls=0;
            output=before;
            assert(runtime_reservations(0x8000000,4096,&memory,&output)==0);
            assert(!memcmp(&output,&before,sizeof output));
            assert(resolved_calls==(scenario==7 || scenario==8));
        }
    }
    scenario=0; console_ok=1;
    assert(runtime_reservations(0x8000000,4096,&memory,&output)==1);
    assert(output.count==0 && output.reservation_free.count==0);
    console_ok=0;
    assert(runtime_reservations(0x8000000,4096,&memory,0)==0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(harness)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
