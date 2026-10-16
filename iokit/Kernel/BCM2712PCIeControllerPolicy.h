/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_CONTROLLER_POLICY_H
#define BCM2712_PCIE_CONTROLLER_POLICY_H
#include "BCM2712PCIeClockPolicy.h"
enum {
    BCM2712_PHY_RC_CONFIGURING = BCM2712_PHY_CLOCK_PREPARING + 1,
    BCM2712_PHY_LINK_TRAINING,
    BCM2712_PHY_CLOCK_FINISHING
};
/* Independent provider obligations, not registry permissions or inferred
 * hardware state. RELEASED must allow a down/training link and must NOT
 * require asserted PERST. Link readiness is checked by the real link core.
 * INITIALIZING must allow the actual bridge reset/RESCAL/SerDes sequence. */
enum bcm2712_controller_lifecycle {
    BCM2712_CONTROLLER_PRECLAIM,
    BCM2712_CONTROLLER_INITIALIZING,
    BCM2712_CONTROLLER_HELD_RESET,
    BCM2712_CONTROLLER_RELEASED
};
static inline int bcm2712_controller_window(uint32_t offset)
{
    for (unsigned i = 0; i < 3; i++)
        if (offset == 0x402c+8*i || offset == 0x4030+8*i ||
            offset == 0x40ac+8*i || offset == 0x40b0+8*i) return 1;
    for (unsigned i = 0; i < 2; i++)
        if (offset == 0x400c+8*i || offset == 0x4010+8*i ||
            offset == 0x4070+4*i || offset == 0x4080+8*i || offset == 0x4084+8*i) return 1;
    return 0;
}
static inline int bcm2712_controller_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    if (phase < BCM2712_PHY_RC_CONFIGURING)
        return bcm2712_clock_access_allowed(phase, bank, offset, width, write);
    if (bank != BCM2712_PHY_BRIDGE || write > 1) return 0;
    if (width == 2) {
        if (offset & 1) return 0;
        if (phase == BCM2712_PHY_RC_CONFIGURING) return offset == 0xbc;
        if (phase == BCM2712_PHY_LINK_TRAINING)
            return offset == 0xdc || (!write && (offset == 0xbc || offset == 0xbe));
        return phase == BCM2712_PHY_CLOCK_FINISHING && !write && offset == 0xbc;
    }
    if (width != 4 || (offset & 3)) return 0;
    if (phase == BCM2712_PHY_RC_CONFIGURING) {
        if (bcm2712_controller_window(offset) || offset == 0x4008 || offset == 0x043c || offset == 0x0188)
            return 1;
        return !write && (offset == 0x04dc ||
            bcm2712_unused_access_allowed(BCM2712_PHY_UNUSED_INSPECTING, bank, offset, width, 0));
    }
    if (phase == BCM2712_PHY_LINK_TRAINING) {
        if (offset == 0x04dc || offset == 0x4304 || offset == 0x4064) return 1;
        return !write && (offset == 0x4008 || offset == 0x043c || offset == 0x0188 || offset == 0x184c ||
            bcm2712_unused_access_allowed(BCM2712_PHY_UNUSED_INSPECTING, bank, offset, width, 0));
    }
    if (phase == BCM2712_PHY_CLOCK_FINISHING) {
        if (offset == 0x04f8 || offset == 0x4304) return 1;
        return !write && (offset == 0x4068 || offset == 0x4064 || offset == 0x04dc || offset == 0x416c);
    }
    return 0;
}
#endif
