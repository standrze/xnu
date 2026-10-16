/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_UBUS_POLICY_H
#define BCM2712_PCIE_UBUS_POLICY_H
#include "BCM2712PCIePHYPolicy.h"

/* Preserve every accepted PHY phase/permission. This separate build adds one
 * phase, not access during COMPLETE/FAILED or any other previous phase. */
enum { BCM2712_PHY_UBUS_CONFIGURING = BCM2712_PHY_FAILED + 1 };
static inline int bcm2712_ubus_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    if (phase != BCM2712_PHY_UBUS_CONFIGURING)
        return bcm2712_phy_access_allowed(phase, bank, offset, width, write);
    if (bank != BCM2712_PHY_BRIDGE || width != 4 || (offset & 3) || write > 1) return 0;
    switch (offset) {
        case 0x40a4: /* UBUS error response control */
        case 0x40a8: /* UBUS timeout */
        case 0x405c: /* Configuration-retry timeout, not config-space access */
        case 0x416c: /* AXI QoS */
        case 0x40a0: /* VDM QoS control */
            return 1;
        case 0x4170: /* Intentional all-ones error data, never read back */
            return write == 1;
        default:
            return 0;
    }
}
#endif
