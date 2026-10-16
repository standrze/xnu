# SPDX-License-Identifier: BSD-2-Clause
"""Exercise the BCM2712 SGI register path with explicit banked GIC substitutes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class KernelSGIModelTests(unittest.TestCase):
    def test_sgi_primitives(self):
        source = (ROOT / "pexpert/arm/pe_fiq.c").read_text()
        functions = source[source.index("uint32_t\npe_rpi5_sgi_local_target("):
                           source.index("#else\nvoid\npe_init_fiq()")]
        functions = functions.replace("__builtin_arm_dsb(DSB_SY);", "barrier_count++;")
        functions = functions.replace("__builtin_arm_dsb(DSB_ISHST);", "barrier_count++;")
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define RPI5_GICD_ITARGETSR0 0x800
#define RPI5_GICD_IPRIORITYR0 0x400
#define RPI5_GICD_ISENABLER0 0x100
#define RPI5_GICD_SGIR 0xf00
#define RPI5_GICD_CTLR 0
#define RPI5_GICC_CTLR 0
#define RPI5_IPI_SGI 1U
static uintptr_t rpi5_gicd_base = 1, rpi5_gicc_base = 2;
static uint32_t registers[1024], writes, barrier_count, last_offset, last_value;
static uint32_t rpi5_mmio_read32(uintptr_t base, unsigned offset) {
    if (base == 2) { assert(offset == 0); return 1; }
    assert(base == 1); return registers[offset / 4];
}
static void rpi5_mmio_write32(uintptr_t base, unsigned offset, uint32_t value) {
    assert(base == 1); writes++; last_offset = offset; last_value = value;
    if (offset == RPI5_GICD_ISENABLER0) registers[offset / 4] |= value;
    else registers[offset / 4] = value;
}
'''
        cases = r'''
int main(void) {
    assert(pe_rpi5_sgi_local_target() == 0);
    registers[0x800 / 4] = 0x04040404;
    assert(pe_rpi5_sgi_local_target() == 4);
    registers[0x804 / 4] = 0x02020202;
    assert(pe_rpi5_sgi_local_target() == 0);
    assert(!pe_rpi5_sgi_enable_local() && !writes);
    registers[0x804 / 4] = 0;
    registers[0] = 1;
    registers[0x400 / 4] = 0x12345678;
    assert(pe_rpi5_sgi_enable_local());
    assert(registers[0x400 / 4] == 0x12348078);
    assert(registers[0x100 / 4] == 2 && barrier_count == 1);
    writes = 0;
    assert(!pe_rpi5_sgi_send(0) && !pe_rpi5_sgi_send(3));
    assert(!pe_rpi5_sgi_send(0x100) && !writes);
    assert(pe_rpi5_sgi_send(4));
    assert(writes == 1 && last_offset == 0xf00 && last_value == 0x40001);
    assert(barrier_count == 2);
    rpi5_gicd_base = 0;
    assert(!pe_rpi5_sgi_send(4) && pe_rpi5_sgi_local_target() == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            test = Path(directory) / "test.c"
            test.write_text(harness + functions + cases)
            binary = test.with_suffix("")
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(test), "-o", str(binary)],
                           check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
