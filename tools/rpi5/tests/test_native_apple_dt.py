# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/rpi5"))
from apple_dt import encode


class NativeAppleDTTests(unittest.TestCase):
    def test_reference_and_atomic_rejection(self):
        source = r'''
#include "apple_dt.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    struct rpi5_adt_property prop={"sample","abc",3};
    struct rpi5_adt_node child={"chosen",&prop,0,1,0};
    const struct rpi5_adt_node *children[]={&child};
    struct rpi5_adt_node root={"device-tree",0,children,0,1};
    unsigned char output[512]; size_t size=999;
    assert(!rpi5_adt_encode(&root,output,sizeof output,&size));
    assert(fwrite(output,1,size,stdout)==size);
    memset(output,0xa5,sizeof output); size_t old=size;
    assert(rpi5_adt_encode(&root,output,size-1,&size)==-1 && size==old);
    for(unsigned i=0;i<sizeof output;i++) assert(output[i]==0xa5);
    children[0]=&root; assert(rpi5_adt_encode(&root,output,sizeof output,&size)==-1); children[0]=&child;
    prop.name="name"; assert(rpi5_adt_encode(&root,output,sizeof output,&size)==-1);
    prop.name="sample"; child.name="bad/path";
    assert(rpi5_adt_encode(&root,output,sizeof output,&size)==-1);
    for(unsigned i=0;i<sizeof output;i++) assert(output[i]==0xa5);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(source)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                            "-I"+str(ROOT/"loader/rpi5"), str(path/"test.c"), str(ROOT/"loader/rpi5/apple_dt.c"),
                            "-o", str(path/"test")], check=True)
            actual = subprocess.check_output([str(path/"test")])
            self.assertEqual(actual, encode({"name":"device-tree","properties":{},"children":[
                {"name":"chosen","properties":{"sample":b"abc"},"children":[]}]}))
