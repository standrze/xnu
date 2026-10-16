/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_RP1_CONFIG_POLICY_H
#define BCM2712_RP1_CONFIG_POLICY_H
#include "BCM2712PCIeControllerPolicy.h"
enum { BCM2712_PHY_RP1_INSPECTING = BCM2712_PHY_CLOCK_FINISHING + 1 };
static inline int bcm2712_rp1_config_access(uint32_t offset, unsigned width, unsigned write)
{
    if (width != 4 || (offset & 3) || write > 1) return 0;
    if (write) return offset == 0x9000;
    return offset == 0x4068 || offset == 0x9000 ||
        (offset >= 0x8000 && offset <= 0x803c);
}
#endif
