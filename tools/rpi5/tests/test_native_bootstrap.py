# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class NativeBootstrapTests(unittest.TestCase):
    def test_mapping_boundaries(self):
        source = r'''
#include "bootstrap.h"
#include <assert.h>
#include <string.h>
int main(void) {
    struct rpi5_range ram={0x2000000,0x28000000}, required={0x3004000,0x4000000};
    struct rpi5_bootstrap_mapping out, prior;
    memset(&prior,0xa5,sizeof prior);
    uint64_t phys=0x2000000, virt=0xfffffe0006000000ull, mem=0x26000000, header=0x3004000;
    assert(!rpi5_bootstrap_mapping(phys,virt,mem,header,ram,&required,1,&out));
    assert(out.entries==18 && out.table_pages==4 && out.physical_start==0x2000000 && out.physical_end==0x26000000);
    out=prior; required.end=0x26000001;
    assert(rpi5_bootstrap_mapping(phys,virt,mem,header,ram,&required,1,&out)==-1 && !memcmp(&out,&prior,sizeof out));
    required.end=0x4000000; ram.start++;
    assert(rpi5_bootstrap_mapping(phys,virt,mem,header,ram,&required,1,&out)==-1); ram.start--;
    assert(rpi5_bootstrap_mapping(phys,virt,0x2000000,header,ram,&required,1,&out)==-1);
    assert(rpi5_bootstrap_mapping(phys,virt+0x4000,mem,header,ram,&required,1,&out)==-1);
    assert(rpi5_bootstrap_mapping(phys,virt,mem,header,ram,0,1,&out)==-1);
    /* Physical mapping crosses a 64 GiB root slot: needs a fifth table page. */
    phys=0xffe000000ull; header=phys+0x1004000; mem=0x8000000;
    ram=(struct rpi5_range){phys,phys+mem}; required=(struct rpi5_range){header,header+0x4000};
    assert(rpi5_bootstrap_mapping(phys,virt,mem,header,ram,&required,1,&out)==-1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(source)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                            "-I"+str(ROOT/"loader/rpi5"), str(path/"test.c"),
                            str(ROOT/"loader/rpi5/bootstrap.c"), "-o", str(path/"test")], check=True)
            subprocess.run([str(path/"test")], check=True)
