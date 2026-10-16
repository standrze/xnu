# SPDX-License-Identifier: BSD-2-Clause
"""Exercise the narrow Apple DT RAMDisk pointer/length contract."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class BoardTreeRAMDiskTests(unittest.TestCase):
    def test_atomic_attachment_and_encoded_record(self):
        source = r'''
#include "board_tree.h"
#include <assert.h>
#include <string.h>
int main(void) {
    const uint64_t ids[]={0};
    struct rpi5_board_tree tree;
    struct rpi5_range uart={0x107d001000ull,0x107d001200ull};
    assert(!rpi5_board_tree_init(ids,1,0,54000000,uart,0,0x200000000ull,&tree));
    unsigned char before[sizeof tree]; memcpy(before,&tree,sizeof tree);
    assert(rpi5_board_tree_ramdisk(&tree,0x8100001,0x8000)==-1);
    assert(rpi5_board_tree_ramdisk(&tree,0x8100000,0)==-1);
    assert(rpi5_board_tree_ramdisk(&tree,0x8100000,0x4001)==-1);
    assert(rpi5_board_tree_ramdisk(&tree,(1ull<<40)-0x4000,0x8000)==-1);
    assert(!memcmp(before,&tree,sizeof tree));
    assert(!rpi5_board_tree_ramdisk(&tree,0x8100000,0x8000));
    assert(tree.image_memory_map.property_count==1);
    assert(tree.image_memory_map.properties==&tree.ramdisk_prop);
    assert(!strcmp(tree.ramdisk_prop.name,"RAMDisk"));
    assert(tree.ramdisk_prop.length==16);
    const unsigned char expected[16]={0,0,0x10,8,0,0,0,0,0,0x80,0,0,0,0,0,0};
    assert(!memcmp(tree.ramdisk_record,expected,16));
    memcpy(before,&tree,sizeof tree);
    assert(rpi5_board_tree_ramdisk(&tree,0x8200000,0x4000)==-1);
    assert(!memcmp(before,&tree,sizeof tree));
    unsigned char encoded[4096]; size_t length=0;
    assert(!rpi5_adt_encode(&tree.root,encoded,sizeof encoded,&length));
    assert(length>16);
    unsigned found=0;
    for(size_t i=0;i+16<=length;i++)
        if(!memcmp(encoded+i,expected,16)) found++;
    assert(found==1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, binary = work / "ramdisk.c", work / "ramdisk"
            program.write_text(source)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                            str(program), *[str(ROOT / "loader/rpi5" / name) for name in
                                           ("board_tree.c", "cpu_tree.c", "serial_tree.c",
                                            "apple_dt.c", "memory_type.c")],
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
