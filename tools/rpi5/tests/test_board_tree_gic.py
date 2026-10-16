# SPDX-License-Identifier: BSD-2-Clause
"""Compare the composed Pi tree's GIC/CPU identity bytes independently."""

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/rpi5"))
from apple_dt import encode


class BoardTreeGICTests(unittest.TestCase):
    def test_watchdog_node_requires_exact_validated_range(self):
        source = r'''
#include "board_tree.h"
#include <assert.h>
int main(void) {
    const uint64_t ids[] = {0};
    struct rpi5_board_tree tree;
    struct rpi5_range uart = {0x107d001000ull, 0x107d001200ull};
    assert(!rpi5_board_tree_init(ids, 1, 0, 54000000, uart, 0, 0x200000000ull, &tree));
    assert(rpi5_board_tree_watchdog(&tree, (struct rpi5_range){0x107d200000ull, 0x107d200307ull}));
    assert(tree.serial.arm_io.child_count == 2);
    assert(!rpi5_board_tree_watchdog(&tree, (struct rpi5_range){0x107d200000ull, 0x107d200308ull}));
    assert(tree.serial.arm_io.child_count == 3);
    assert(tree.serial.children[2] == &tree.watchdog);
    assert(rpi5_board_tree_watchdog(&tree, (struct rpi5_range){0x107d200000ull, 0x107d200308ull}));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, binary = work / "watchdog.c", work / "watchdog"
            program.write_text(source)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                            str(program), *[str(ROOT / "loader/rpi5" / name) for name in
                                           ("board_tree.c", "cpu_tree.c", "serial_tree.c",
                                            "apple_dt.c", "memory_type.c")],
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_composed_gic_and_cpu_properties(self):
        source = r'''
#include "board_tree.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    const uint64_t ids[]={0};
    struct rpi5_board_tree tree;
    struct rpi5_range uart={0x107d001000ull,0x107d001200ull};
    assert(!rpi5_board_tree_init(ids,1,0,54000000,uart,0,0x200000000ull,&tree));
    unsigned char encoded[4096]; size_t size=0;
    assert(!rpi5_adt_encode(&tree.root,encoded,sizeof encoded,&size));
    assert(fwrite(encoded,1,size,stdout)==size);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, binary = work / "board.c", work / "board"
            program.write_text(source)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                            str(program), *[str(ROOT / "loader/rpi5" / name) for name in
                                           ("board_tree.c", "cpu_tree.c", "serial_tree.c",
                                            "apple_dt.c", "memory_type.c")],
                            "-o", str(binary)], check=True)
            actual = subprocess.check_output([str(binary)])

        one_cpu = {"name": "cpu0", "properties": {
            "reg": struct.pack("<I", 0), "state": b"running\0",
            "timebase-frequency": struct.pack("<I", 54000000),
            "device_type": b"cpu\0"}, "children": []}
        expected = {"name": "device-tree", "properties": {
            "compatible": b"raspberrypi,5-model-b\0brcm,bcm2712\0"}, "children": [
            {"name": "chosen", "properties": {
                "dram-base": struct.pack("<Q", 0),
                "dram-size": struct.pack("<Q", 0x200000000)}, "children": [
                {"name": "memory-map", "properties": {}, "children": []}]},
            {"name": "cpus", "properties": {}, "children": [one_cpu]},
            {"name": "arm-io", "properties": {
                "device_type": b"soc\0",
                "ranges": struct.pack("<QQQ", 0, 0x107c000000, 0x4000000)},
                "children": [
                    {"name": "uart10", "properties": {
                        "compatible": b"arm,pl011\0",
                        "reg": struct.pack("<QQ", 0x1001000, 0x200),
                        "AAPL,phandle": struct.pack("<I", 1)}, "children": []},
                    {"name": "gic", "properties": {
                        "compatible": b"arm,gic-400\0",
                        "reg": struct.pack("<QQQQ", 0x3ff9000, 0x1000,
                                           0x3ffa000, 0x2000)}, "children": []}]},
            {"name": "defaults", "properties": {
                "serial-device": struct.pack("<I", 1)}, "children": []}]}
        self.assertEqual(actual, encode(expected))


if __name__ == "__main__":
    unittest.main()
