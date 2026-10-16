from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class SeedMetadataTests(unittest.TestCase):
    def test_metadata_does_not_dereference_property(self):
        code=(ROOT/'loader/rpi5/probe_main.c').read_text()
        function='static int runtime_seed_metadata('+code.split('static int runtime_seed_metadata(',1)[1].split('\nstatic int runtime_cpus(',1)[0]
        harness=r'''
#include "fdt.h"
#include <assert.h>
static int calls, mode, lengths;
static int text(const char *s) { assert(s); return 1; }
static int hex(uint64_t value) { assert(value==256); lengths++; return 1; }
int rpi5_fdt_property(const void *b,size_t n,const char *path,const char *name,struct rpi5_fdt_property *p) {
    assert(b==(void *)1 && n==4096 && path && name); calls++;
    if(mode) return mode;
    p->offset=0xffffffffu; p->length=256; return 0;
}
'''+function+r'''
int main(void) {
    assert(runtime_seed_metadata(1,4096)); assert(calls==3 && lengths==3);
    calls=lengths=0; mode=-2;
    assert(runtime_seed_metadata(1,4096)); assert(calls==3 && !lengths);
    calls=0; mode=-1;
    assert(!runtime_seed_metadata(1,4096)); assert(calls==1 && !lengths);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(harness)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(ROOT/'loader/rpi5'),str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
