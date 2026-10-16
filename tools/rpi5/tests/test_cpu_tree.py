# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/rpi5'))
from apple_dt import encode


class CpuTreeTests(unittest.TestCase):
    def test_physical_ids_boot_cpu_and_atomic_validation(self):
        code=r'''
#include "cpu_tree.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    uint64_t ids[]={0,0x100,0x200,0x300};
    struct rpi5_cpu_tree tree;
    assert(!rpi5_cpu_tree_init(ids,4,0x200,54000000,&tree));
    unsigned char out[4096]; size_t n;
    assert(!rpi5_adt_encode(&tree.root,out,sizeof out,&n));
    assert(fwrite(out,1,n,stdout)==n);
    unsigned char prior[sizeof tree]; memcpy(prior,&tree,sizeof tree);
    assert(rpi5_cpu_tree_init(ids,0,0,54000000,&tree)==-1);
    assert(rpi5_cpu_tree_init(ids,5,0,54000000,&tree)==-1);
    assert(rpi5_cpu_tree_init(ids,4,0,0,&tree)==-1);
    assert(rpi5_cpu_tree_init(ids,4,0x400,54000000,&tree)==-1);
    const uint64_t bad[]={1,0x400,0x100000000ull,0};
    for(unsigned i=0;i<4;i++) {
        ids[1]=bad[i];
        assert(rpi5_cpu_tree_init(ids,4,0,54000000,&tree)==-1);
    }
    assert(!memcmp(prior,&tree,sizeof tree));
    ids[0]=0x300;
    assert(!rpi5_cpu_tree_init(ids,1,0x300,54000000,&tree));
    assert(tree.root.child_count==1 && !strcmp(tree.cpu[0].name,"cpu3"));
    assert(!strcmp(tree.properties[0][1].data,"running"));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),str(ROOT/'loader/rpi5/cpu_tree.c'),
                            str(ROOT/'loader/rpi5/apple_dt.c'),'-o',str(p/'test')],check=True)
            raw=subprocess.check_output([str(p/'test')])
            expected={'name':'cpus','properties':{},'children':[
                {'name':f'cpu{i}','properties':{
                    'reg':struct.pack('<I',i<<8),
                    'state':b'running\0' if i==2 else b'stopped\0',
                    'timebase-frequency':struct.pack('<I',54000000),
                    'device_type':b'cpu\0'},'children':[]}
                for i in range(4)]}
            self.assertEqual(raw,encode(expected))
