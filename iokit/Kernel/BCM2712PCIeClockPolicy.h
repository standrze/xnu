/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_CLOCK_POLICY_H
#define BCM2712_PCIE_CLOCK_POLICY_H
#include "BCM2712PCIeQoSPolicy.h"
enum { BCM2712_PHY_CLOCK_PREPARING = BCM2712_PHY_QOS_CONFIGURING + 1 };
static inline int bcm2712_clock_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    if (phase != BCM2712_PHY_CLOCK_PREPARING)
        return bcm2712_qos_access_allowed(phase, bank, offset, width, write);
    if (bank != BCM2712_PHY_BRIDGE || width != 4 || write > 1 || (offset & 3)) return 0;
    if (offset == 0x04dc) return 1;
    return !write && (offset == 0x4068 || offset == 0x4064 || offset == 0x4304 || offset == 0x416c);
}
#endif
