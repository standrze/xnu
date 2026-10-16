# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RuntimePsciFlowTests(unittest.TestCase):
    def test_required_features_and_secondary_failure(self):
        source = (ROOT/'loader/rpi5/probe_main.c').read_text()
        function = 'static int psci_secondary_probe(' + source.split(
            'static int psci_secondary_probe(', 1)[1].split(
            '\nvoid probe_el1_main(', 1)[0]
        code = r'''
#include "fdt.h"
#include <assert.h>
static uint64_t version, cpu_on, cpu_off, affinity;
static int console_ok, secondary_ok, inventory_ok, calls, inventories;
static int text(const char *s) { (void)s; return console_ok; }
static int hex(uint64_t v) { (void)v; return console_ok; }
static uint64_t rpi5_psci_query(uint64_t fid, uint64_t arg) {
    if (fid==0x84000000u) return version;
    assert(fid==0x8400000au);
    if (arg==0x84000002u) return cpu_off;
    assert(arg==0xc4000003u || arg==0xc4000004u);
    return arg==0xc4000003u ? cpu_on : affinity;
}
static int psci_affinity_inventory(const struct rpi5_fdt_cpus *c) {
    (void)c; ++inventories; return inventory_ok;
}
static int start_secondaries(const struct rpi5_fdt_cpus *c) {
    (void)c; ++calls; return secondary_ok;
}
''' + function + r'''
int main(void) {
    struct rpi5_fdt_cpus cpus={0};
    const uint64_t versions[]={0,2,0xffffffffu,0x80010000u,0x10000,0x10001,
        0xffffffff00010001ull};
    const uint64_t features[]={0,1,0xffffffffu,0xffffffff00000000ull};
    for (unsigned v=0;v<7;v++) for (unsigned c=0;c<4;c++)
    for (unsigned o=0;o<4;o++) for (unsigned a=0;a<4;a++) for (console_ok=0;console_ok<2;console_ok++)
    for (secondary_ok=0;secondary_ok<2;secondary_ok++)
    for (inventory_ok=0;inventory_ok<2;inventory_ok++) {
        version=versions[v]; cpu_on=features[c]; affinity=features[a]; cpu_off=features[o];
        calls=inventories=0;
        int prerequisites=console_ok && v>=4 && (c==0 || c==3) && (a==0 || a==3) && (o==0 || o==3);
        assert(psci_secondary_probe(&cpus)==(prerequisites && inventory_ok && secondary_ok));
        assert(calls==(prerequisites && inventory_ok) && inventories==prerequisites);
    }
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
