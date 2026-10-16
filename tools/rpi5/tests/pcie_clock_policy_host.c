/* SPDX-License-Identifier: BSD-2-Clause */
#include "BCM2712PCIeClockPolicy.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
    unsigned reads = 0, writes = 0;
    const unsigned widths[] = {0,1,2,3,4,8};
    for (unsigned phase = 0; phase <= BCM2712_PHY_CLOCK_PREPARING+2; phase++)
    for (unsigned bank = 0; bank < 5; bank++) for (unsigned i = 0; i < 6; i++)
    for (unsigned write = 0; write < 3; write++) for (uint32_t off = 0; off < 0x10000; off++) {
        int actual = bcm2712_clock_access_allowed(phase, bank, off, widths[i], write);
        if (phase != BCM2712_PHY_CLOCK_PREPARING) {
            assert(actual == bcm2712_qos_access_allowed(phase, bank, off, widths[i], write)); continue;
        }
        int expected = bank == 0 && widths[i] == 4 && write < 2 &&
            (off == 0x04dc || (!write && (off == 0x4068 || off == 0x4064 || off == 0x4304 || off == 0x416c)));
        assert(actual == expected);
        if (actual) { if (write) writes++; else reads++; }
    }
    assert(reads == 5 && writes == 1);
    assert(!bcm2712_clock_access_allowed(BCM2712_PHY_CLOCK_PREPARING,0,UINT32_MAX,4,0));
    puts("PCIE_CLOCK_POLICY_PASS READS=5 WRITES=1 NO_MMIO=1");
    return 0;
}
