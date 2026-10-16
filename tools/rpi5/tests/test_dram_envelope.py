# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class DramEnvelopeTests(unittest.TestCase):
    def test_managed_span_guard(self):
        arm=(ROOT/'osfmk/arm/arm_init.c').read_text()
        start=arm.index('\tif (!args->memSize || args->physBase >= (1ULL << 40)')
        guard=arm[start:arm.index('\n#endif',start)]
        code='''
#include <stdint.h>
#include <assert.h>
#include "arm64/rpi5_memory_map.h"
static struct rpi5_kernel_memory_map map={
    .type={1,1,2}, .start={0,0x40000000,0x107d000000},
    .end={0x3fc00000,0x200000000,0x107d004000}, .count=3};
static unsigned rpi5_physical_memory_type(uint64_t a,uint64_t b) {
    return rpi5_map_type(&map,a,b);
}
#define panic(...) return 0
static int check(uint64_t base,uint64_t size) {
    struct { uint64_t physBase,memSize; } value={base,size},*args=&value;
'''+guard+'''
    return 1;
}
int main(void) {
    assert(check(0x6000000,0xa000000));
    assert(check(0,0x3fc00000));
    assert(check(0x40000000,0x1c0000000));
    assert(!check(0,0));
    assert(!check(0,0x40000000));
    assert(!check(0x3fc00000,0x4000));
    assert(!check(0x3fbfc000,0x8000));
    assert(!check(0x107d000000,0x4000));
    assert(!check(1,0x4000));
    assert(!check(0,0x4001));
    assert(!check(UINT64_MAX,0x4000));
    assert(!check(0x4000,UINT64_MAX));
    assert(!check(1ULL<<40,0x4000));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'osfmk'),
                str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_actual_board_guards_and_unchanged_other_platform_sentinel(self):
        arm=(ROOT/'osfmk/arm/arm_init.c').read_text()
        blocks=re.findall(r'#if defined\(ARM64_BOARD_CONFIG_BCM2712\).*?#endif',arm,re.S)
        base=next(x for x in blocks if 'dram-base must be' in x)
        size=next(x for x in blocks if 'invalid DRAM envelope' in x)
        pmap=(ROOT/'osfmk/arm/pmap/pmap.c').read_text()
        start=pmap.index('#if defined(ARM64_BOARD_CONFIG_BCM2712)\n\t/* Pi DRAM')
        guard=pmap[start:pmap.index('\n\tconst bool first_page_is_dram',start)]
        code='''
#include <assert.h>
#include <stdint.h>
#define panic(...) return 0
#define __improbable(x) (x)
static int initialized(uint64_t gDramBase,uint64_t gDramSize) {
    (void)gDramBase;
'''+guard+'''\nreturn 1; }
static int envelope(unsigned base_width,unsigned size_width,unsigned long b,unsigned long s) {
    const unsigned long *dram_base=&b, *dram_size=&s;
    unsigned dt_entry_size=base_width;
'''+base+'''\ndt_entry_size=size_width;
'''+size+'''\nreturn 1; }
int main(void) {
    assert(sizeof(unsigned long)==8);
    assert(!initialized(0,0));
    assert(!initialized(0x80000,0));
    assert(initialized(0x80000,0x100000));
#ifdef ARM64_BOARD_CONFIG_BCM2712
    assert(initialized(0,0x200000000));
    assert(envelope(8,8,0,0x200000000));
    assert(envelope(8,8,(1ULL<<40)-1,1));
    assert(!envelope(4,8,0,0x200000000));
    assert(!envelope(8,4,0,0x200000000));
    assert(!envelope(8,8,0,0));
    assert(!envelope(8,8,1ULL<<40,1));
    assert(!envelope(8,8,(1ULL<<40)-1,2));
    assert(!envelope(8,8,UINT64_MAX,UINT64_MAX));
#else
    assert(!initialized(0,0x200000000));
#endif
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            for board in ([],['-DARM64_BOARD_CONFIG_BCM2712=1']):
                subprocess.run(['xcrun','clang','-fsanitize=address,undefined',*board,
                                str(p/'test.c'),'-o',str(p/'test')],check=True)
                subprocess.run([str(p/'test')],check=True)
