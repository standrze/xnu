/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include "BCM2712PCIeUBUSPolicy.h"

int main(void)
{
    unsigned accepted = 0;
    const unsigned widths[] = {0, 1, 2, 4, 8};
    for (unsigned phase = 0; phase <= BCM2712_PHY_UBUS_CONFIGURING + 2; phase++)
    for (unsigned bank = 0; bank < 5; bank++)
    for (unsigned wi = 0; wi < sizeof widths / sizeof widths[0]; wi++)
    for (unsigned write = 0; write < 3; write++)
    for (uint32_t off = 0; off <= 0xa000; off++) {
        int allowed = bcm2712_ubus_access_allowed(phase, bank, off, widths[wi], write);
        if (phase != BCM2712_PHY_UBUS_CONFIGURING)
            assert(allowed == bcm2712_phy_access_allowed(phase, bank, off, widths[wi], write));
        else {
            int reg = off == 0x40a4 || off == 0x40a8 || off == 0x405c || off == 0x416c ||
                off == 0x40a0 || (off == 0x4170 && write == 1);
            assert(allowed == (bank == BCM2712_PHY_BRIDGE && widths[wi] == 4 && write < 2 && reg));
            accepted += allowed;
        }
    }
    assert(accepted == 11);
    assert(!bcm2712_ubus_access_allowed(BCM2712_PHY_UBUS_CONFIGURING, BCM2712_PHY_BRIDGE, UINT32_MAX, 4, 1));
    printf("PCIE_UBUS_POLICY_PASS NEW_ACCESSES=%u NO_MMIO=1\n", accepted);
    return 0;
}
