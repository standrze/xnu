/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_UNUSED_POLICY_H
#define BCM2712_PCIE_UNUSED_POLICY_H
#include "BCM2712PCIeUBUSPolicy.h"
enum { BCM2712_PHY_UNUSED_INSPECTING = BCM2712_PHY_UBUS_CONFIGURING + 1 };
static inline int bcm2712_unused_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    if (phase != BCM2712_PHY_UNUSED_INSPECTING)
        return bcm2712_ubus_access_allowed(phase, bank, offset, width, write);
    if (bank != BCM2712_PHY_BRIDGE || width != 4 || write || (offset & 3)) return 0;
    if (offset == 0x4068 || offset == 0x4064 || offset == 0x4304) return 1;
    for (unsigned i = 0; i < 7; i++)
        if (offset == 0x40d4 + 8 * i || offset == 0x410c + 8 * i) return 1;
    for (unsigned slot = 2; slot < 4; slot++)
        if (offset == 0x4070 + 4 * slot || offset == 0x4080 + 8 * slot ||
            offset == 0x4084 + 8 * slot) return 1;
    return 0;
}
#endif
