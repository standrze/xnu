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


class SerialTreeTests(unittest.TestCase):
    def test_native_offsets_and_selection(self):
        code=r'''
#include "serial_tree.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    struct rpi5_serial_tree tree;
    struct rpi5_range uart={0x107d001000ull,0x107d001200ull};
    assert(!rpi5_serial_tree_init(uart,0x12345678,&tree));
    const struct rpi5_adt_node *children[]={&tree.arm_io,&tree.defaults};
    struct rpi5_adt_node root={"device-tree",0,children,0,2};
    unsigned char out[2048]; size_t n;
    assert(!rpi5_adt_encode(&root,out,sizeof out,&n));
    assert(fwrite(out,1,n,stdout)==n);
    unsigned char prior[sizeof tree]; memcpy(prior,&tree,sizeof tree);
    assert(rpi5_serial_tree_init(uart,0,&tree)==-1);
    assert(rpi5_serial_tree_init(uart,UINT32_MAX,&tree)==-1);
    uart.end++; assert(rpi5_serial_tree_init(uart,1,&tree)==-1);
    uart.end--; uart.start--; assert(rpi5_serial_tree_init(uart,1,&tree)==-1);
    assert(!memcmp(prior,&tree,sizeof tree));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),str(ROOT/'loader/rpi5/serial_tree.c'),
                            str(ROOT/'loader/rpi5/apple_dt.c'),'-o',str(p/'test')],check=True)
            raw=subprocess.check_output([str(p/'test')])
            phandle=struct.pack('<I',0x12345678)
            expected={'name':'device-tree','properties':{},'children':[
                {'name':'arm-io','properties':{'device_type':b'soc\0',
                 'ranges':struct.pack('<QQQ',0,0x107c000000,0x4000000)},'children':[
                    {'name':'uart10','properties':{'compatible':b'arm,pl011\0',
                     'reg':struct.pack('<QQ',0x1001000,0x200),'AAPL,phandle':phandle},'children':[]}]},
                {'name':'defaults','properties':{'serial-device':phandle},'children':[]}]}
            self.assertEqual(raw,encode(expected))
