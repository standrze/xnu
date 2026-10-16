/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include "BCM2712PCIeUnusedPolicy.h"
int main(void)
{
    const uint32_t offsets[] = {0x4068, 0x4064, 0x4304,
        0x40d4, 0x410c, 0x40dc, 0x4114, 0x40e4, 0x411c, 0x40ec, 0x4124,
        0x40f4, 0x412c, 0x40fc, 0x4134, 0x4104, 0x413c,
        0x4078, 0x4090, 0x4094, 0x407c, 0x4098, 0x409c};
    unsigned accepted = 0;
    const unsigned widths[] = {0, 1, 2, 4, 8};
    for (unsigned phase = 0; phase <= BCM2712_PHY_UNUSED_INSPECTING + 2; phase++)
    for (unsigned bank = 0; bank < 5; bank++)
    for (unsigned wi = 0; wi < sizeof widths / sizeof widths[0]; wi++)
    for (unsigned write = 0; write < 3; write++)
    for (uint32_t off = 0; off <= 0xa000; off++) {
        int allowed = bcm2712_unused_access_allowed(phase, bank, off, widths[wi], write);
        if (phase != BCM2712_PHY_UNUSED_INSPECTING)
            assert(allowed == bcm2712_ubus_access_allowed(phase, bank, off, widths[wi], write));
        else {
            unsigned reg = 0;
            for (unsigned i = 0; i < sizeof offsets / sizeof offsets[0]; i++) reg += off == offsets[i];
            assert(allowed == (bank == BCM2712_PHY_BRIDGE && widths[wi] == 4 && !write && reg == 1));
            accepted += allowed;
        }
    }
    assert(accepted == 23);
    assert(!bcm2712_unused_access_allowed(BCM2712_PHY_UNUSED_INSPECTING, BCM2712_PHY_BRIDGE, UINT32_MAX, 4, 0));
    printf("PCIE_UNUSED_POLICY_PASS NEW_READS=%u NEW_WRITES=0 NO_MMIO=1\n", accepted);
    return 0;
}
