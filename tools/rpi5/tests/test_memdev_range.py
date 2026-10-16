"""Exercise 4 KiB memdev units and overflow-safe I/O bounds."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class MemdevRangeTests(unittest.TestCase):
    def test_compiled_range_math(self):
        source = r'''
#include <dev/memdev_range.h>
#include <stdint.h>
#include <limits.h>
int main(void) {
    uint64_t offset, available;
    const uint64_t large = memdev_size_bytes(1U << 20);
    if (large != (1ULL << 32)) return 1;
    if (memdev_size_bytes(UINT32_MAX) != ((uint64_t)UINT32_MAX << 12)) return 2;
    if (!memdev_block_offset(large / 512, 512, &offset) || offset != large) return 3;
    if (!memdev_available_bytes(offset, large, &available) || available) return 4;
    if (memdev_available_bytes(large + 1, large, &available)) return 5;
    if (!memdev_available_bytes(large - 7, large, &available) || available != 7) return 6;
    if (memdev_block_offset(UINT64_MAX, 512, &offset)) return 7;
    if (memdev_block_offset(1, 0, &offset)) return 8;
    if (!memdev_block_offset(0, 512, &offset) || offset) return 9;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "range.c"
            out = Path(directory) / "range"
            src.write_text(source)
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra",
                            "-Werror", "-I", str(ROOT / "bsd"), str(src),
                            "-o", str(out)], check=True)
            subprocess.run([str(out)], check=True)

    def test_io_paths_use_checked_ranges(self):
        source = (ROOT / "bsd/dev/memdev.c").read_text()
        self.assertIn("memdev_available_bytes((uint64_t)uio->uio_offset", source)
        self.assertIn("memdev_block_offset((uint64_t)buf_blkno(bp)", source)
        self.assertIn("memdev_available_bytes(blkoff, disk_bytes", source)
        self.assertIn("if (buf_count(bp) > available)", source)
        self.assertIn("*o = (memdev_size_bytes(mdev[devid].mdSize)", source)
        self.assertIn("if (*f < DEV_BSIZE || *f > INT_MAX)", source)
        self.assertIn("checked_size = memdev_size_bytes(mdev[devid].mdSize)", source)
        self.assertIn("*size = checked_size", source)


if __name__ == "__main__":
    unittest.main()
