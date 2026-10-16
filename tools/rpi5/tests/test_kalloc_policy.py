"""Run the production zone policy against the captured Pi type distribution."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class KallocPolicyTests(unittest.TestCase):
    def test_captured_distribution_keeps_policy_and_fits_scratch(self):
        source = (ROOT / 'osfmk/kern/kalloc.c').read_text()
        begin = source.index('static uint16_t\nkalloc_type_distribute_budget(')
        end = source.index('__startup_func\nstatic void\nkalloc_type_create_zone_for_size(', begin)
        policy = source[begin:end]
        # serial-capture-9yn_nm4_: size, total types, unique signatures,
        # assigned zones, signature zones, type zones.
        rows = [
            (16,29,3,13,2,11), (32,67,11,31,8,23), (48,65,29,32,18,14),
            (64,37,25,23,17,6), (80,29,27,18,17,1), (96,28,24,18,16,2),
            (128,31,28,19,18,1), (160,47,19,24,12,12), (192,18,18,12,12,0),
            (224,26,17,15,11,4), (256,8,8,6,6,0), (288,4,4,3,3,0),
            (368,6,6,5,5,0), (400,4,4,3,3,0), (512,13,13,9,9,0),
            (576,3,3,2,2,0), (768,2,2,2,2,0), (1024,11,8,8,6,2),
            (1152,1,1,1,1,0), (1280,1,1,1,1,0), (1664,1,1,1,1,0),
            (2048,3,2,3,2,1), (4096,10,9,8,7,1), (6144,2,2,2,2,0),
            (8192,0,0,0,0,0), (12288,0,0,0,0,0), (16384,1,1,1,1,0),
            (24576,0,0,0,0,0), (32768,0,0,0,0,0),
        ]
        code = '''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define __startup_func
#define MAX_K_ZONE(x) 29
#define KT_OPTIONS_DEBUG 2
static unsigned kt_options;
struct nzones_with_idx { uint16_t nzones, idx; };
static const uint16_t kt_zone_cfg[29] = {'''
        code += ','.join(str(r[0]) for r in rows) + '};\n' + policy
        code += '\nint main(void) {\nuint16_t rows[29][6] = {'
        code += ','.join('{' + ','.join(map(str, r)) + '}' for r in rows) + '};\n'
        code += '''
    uint16_t sig[29], types[29], zs[29] = {0}, zt[29] = {0};
    for (unsigned i=0;i<29;i++) {
        sig[i]=rows[i][2]; types[i]=rows[i][1]-sig[i];
    }
    assert(kalloc_type_apply_policy(sig,types,zs,zt,260)==0);
    unsigned total=0, max_slots=0;
    for (unsigned i=0;i<29;i++) {
        assert(zs[i]==rows[i][4] && zt[i]==rows[i][5]);
        total+=zs[i]+zt[i];
        if (max_slots<zs[i]+zt[i]+1u) max_slots=zs[i]+zt[i]+1u;
    }
    assert(total==260 && max_slots==33);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined',str(path/'test.c'),
                            '-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True,timeout=5)
        self.assertIn('#define KT_ZONES_FOR_SIZE_SIZE (MAX_ZONES + 1)', source)
        self.assertIn('static __startup_data zone_t rpi5_kt_zones_for_size[KT_ZONES_FOR_SIZE_SIZE];', source)
        self.assertIn('bzero(rpi5_kt_zones_for_size, sizeof(rpi5_kt_zones_for_size));', source)
        self.assertIn('assert(n_zones_sig + n_zones_type + 1 <= KT_ZONES_FOR_SIZE_SIZE);', source)


if __name__ == '__main__':
    unittest.main()
