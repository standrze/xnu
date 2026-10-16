"""Exercise the board-scoped mockfs pager choice with compiled C."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "bsd/miscfs/mockfs/mockfs_paging_policy.h"
VFSOPS = ROOT / "bsd/miscfs/mockfs/mockfs_vfsops.c"


class MockfsPagingPolicyTests(unittest.TestCase):
    def test_board_and_build_scoping(self):
        source = r'''
#include <miscfs/mockfs/mockfs_paging_policy.h>
int main(void) {
    return mockfs_use_direct_memdev_pager(0) != 0 ||
        mockfs_use_direct_memdev_pager(1) != EXPECT_DIRECT;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "policy.c"
            binary = Path(directory) / "policy"
            program.write_text(source)
            for flags, expected in (
                ([], 1),
                (["-DDEVELOPMENT=1"], 1),
                (["-DARM64_BOARD_CONFIG_BCM2712=1"], 1),
                (["-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=0"], 1),
                (["-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=1"], 0),
            ):
                with self.subTest(flags=flags):
                    subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra",
                                    "-Werror", "-I", str(ROOT / "bsd"),
                                    f"-DEXPECT_DIRECT={expected}", *flags,
                                    str(program), "-o", str(binary)], check=True)
                    subprocess.run([str(binary)], check=True)

    def test_mount_flag_drives_both_direct_map_and_pagein_choice(self):
        source = VFSOPS.read_text()
        self.assertIn("mockfs_use_direct_memdev_pager(memdev_info.mi_mdev)", source)
        node = (ROOT / "bsd/miscfs/mockfs/mockfs_fsnode.c").read_text()
        vnops = (ROOT / "bsd/miscfs/mockfs/mockfs_vnops.c").read_text()
        self.assertIn("(mockfs_mnt->mockfs_memory_backed)", node)
        self.assertIn("if (mockfs_mnt->mockfs_memory_backed)", vnops)
        self.assertIn("return cluster_pagein(", vnops)


if __name__ == "__main__":
    unittest.main()
