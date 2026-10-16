/* SPDX-License-Identifier: BSD-2-Clause */
#include "BCM2712PCIeControllerPolicy.h"
#include <assert.h>
#include <stdio.h>
static int window(uint32_t x)
{
    const uint32_t offsets[] = {0x402c,0x4030,0x40ac,0x40b0,0x4034,0x4038,0x40b4,0x40b8,
        0x403c,0x4040,0x40bc,0x40c0,0x400c,0x4010,0x4070,0x4080,0x4084,
        0x4014,0x4018,0x4074,0x4088,0x408c};
    for (unsigned i = 0; i < sizeof offsets/sizeof offsets[0]; i++) if (x == offsets[i]) return 1;
    return 0;
}
static int unused(uint32_t x)
{
    const uint32_t offsets[] = {0x40d4,0x410c,0x40dc,0x4114,0x40e4,0x411c,0x40ec,0x4124,
        0x40f4,0x412c,0x40fc,0x4134,0x4104,0x413c,0x4078,0x4090,0x4094,
        0x407c,0x4098,0x409c,0x4068,0x4064,0x4304};
    for (unsigned i = 0; i < sizeof offsets/sizeof offsets[0]; i++) if (x == offsets[i]) return 1;
    return 0;
}
int main(void)
{
    unsigned counts[3][2] = {{0}};
    const unsigned widths[] = {0,1,2,3,4,8};
    for (unsigned phase = 0; phase <= BCM2712_PHY_CLOCK_FINISHING+2; phase++)
    for (unsigned bank = 0; bank < 5; bank++) for (unsigned i = 0; i < 6; i++)
    for (unsigned write = 0; write < 3; write++) for (uint32_t x = 0; x < 0x10000; x++) {
        int actual = bcm2712_controller_access_allowed(phase,bank,x,widths[i],write), expected = 0;
        if (phase < BCM2712_PHY_RC_CONFIGURING) {
            assert(actual == bcm2712_clock_access_allowed(phase,bank,x,widths[i],write)); continue;
        }
        if (bank == 0 && write < 2) {
            if (phase == BCM2712_PHY_RC_CONFIGURING) {
                if (widths[i] == 2) expected = x == 0xbc;
                if (widths[i] == 4) expected = window(x) || x == 0x4008 || x == 0x043c || x == 0x0188 ||
                    (!write && (x == 0x04dc || unused(x)));
            }
            if (phase == BCM2712_PHY_LINK_TRAINING) {
                if (widths[i] == 2) expected = x == 0xdc || (!write && (x == 0xbc || x == 0xbe));
                if (widths[i] == 4) expected = x == 0x04dc || x == 0x4304 || x == 0x4064 ||
                    (!write && (x == 0x4008 || x == 0x043c || x == 0x0188 || x == 0x184c || unused(x)));
            }
            if (phase == BCM2712_PHY_CLOCK_FINISHING) {
                if (widths[i] == 2) expected = !write && x == 0xbc;
                if (widths[i] == 4) expected = x == 0x04f8 || x == 0x4304 ||
                    (!write && (x == 0x4068 || x == 0x4064 || x == 0x04dc || x == 0x416c));
            }
        }
        assert(actual == expected);
        if (actual) counts[phase-BCM2712_PHY_RC_CONFIGURING][write]++;
    }
    assert(counts[0][0] == 50 && counts[0][1] == 26);
    assert(counts[1][0] == 31 && counts[1][1] == 4);
    assert(counts[2][0] == 7 && counts[2][1] == 2);
    assert(!bcm2712_controller_access_allowed(UINT32_MAX,0,0xbc,2,1));
    assert(!bcm2712_controller_access_allowed(BCM2712_PHY_LINK_TRAINING,0,UINT32_MAX,4,0));
    puts("PCIE_CONTROLLER_POLICY_PASS RC=50/26 LINK=31/4 CLOCK=7/2 NO_MMIO=1");
    return 0;
}
