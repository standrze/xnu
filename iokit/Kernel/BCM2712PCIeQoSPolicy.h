/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_QOS_POLICY_H
#define BCM2712_PCIE_QOS_POLICY_H
#include "BCM2712PCIeUnusedPolicy.h"
enum { BCM2712_PHY_QOS_CONFIGURING = BCM2712_PHY_UNUSED_INSPECTING + 1 };
static inline int bcm2712_qos_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    if (phase != BCM2712_PHY_QOS_CONFIGURING)
        return bcm2712_unused_access_allowed(phase, bank, offset, width, write);
    if (bank != BCM2712_PHY_BRIDGE || width != 4 || write > 1 || (offset & 3)) return 0;
    if (offset == 0x4068 || offset == 0x4064 || offset == 0x4304 || offset == 0x416c) return !write;
    if (offset == 0x40a0 || offset == 0x4168 || offset == 0x4164 || offset == 0x0a0c || offset == 0x0a20)
        return 1;
    return offset >= 0x4144 && offset <= 0x4160; /* Eight aligned per-TC words. */
}
#endif
