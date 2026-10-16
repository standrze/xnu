/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_PHY_POLICY_H
#define BCM2712_PCIE_PHY_POLICY_H
#include <stdint.h>

/* Shared by the real kernel transport and native boundary tests. This is
 * address/phase restriction, NEVER accessibility, power or recovery admission. */
enum bcm2712_phy_bank { BCM2712_PHY_BRIDGE, BCM2712_PHY_RESCAL, BCM2712_PHY_RESET };
enum bcm2712_phy_phase {
    BCM2712_PHY_EMPTY, BCM2712_PHY_PREPARED, BCM2712_PHY_RESETTING,
    BCM2712_PHY_CALIBRATING, BCM2712_PHY_CONFIGURING,
    BCM2712_PHY_COMPLETE, BCM2712_PHY_FAILED
};
struct bcm2712_phy_mapping {
    uint64_t physical, bytes, page, page_bytes, offset;
};
static inline int bcm2712_phy_mapping_plan(unsigned bank, uint64_t base,
    uint64_t bytes, struct bcm2712_phy_mapping *out)
{
    const uint64_t bases[3] = {UINT64_C(0x1000120000), UINT64_C(0x1000119500), UINT64_C(0x1001504318)};
    const uint64_t lengths[3] = {UINT64_C(0x9310), UINT64_C(0x10), UINT64_C(0x30)};
    if (!out || bank >= 3 || base != bases[bank] || bytes != lengths[bank]) return 0;
    struct bcm2712_phy_mapping result;
    result.physical = base;
    result.bytes = bytes;
    result.page = base & ~UINT64_C(0x3fff);
    result.offset = base - result.page;
    result.page_bytes = (result.offset + bytes + UINT64_C(0x3fff)) & ~UINT64_C(0x3fff);
    *out = result;
    return 1;
}
static inline int bcm2712_phy_access_allowed(unsigned phase, unsigned bank,
    uint32_t offset, unsigned width, unsigned write)
{
    /* All PHY registers are true aligned 32-bit accesses. No byte/halfword
     * emulation, broad aperture access, endpoint config or BAR access. */
    if (width != 4 || (offset & 3) || write > 1) return 0;
    if (phase == BCM2712_PHY_RESETTING && bank == BCM2712_PHY_RESET)
        return write ? offset == 0x18 || offset == 0x1c : offset == 0x20;
    if (phase == BCM2712_PHY_CALIBRATING && bank == BCM2712_PHY_RESCAL)
        return offset == 0 || (!write && offset == 8);
    if (phase == BCM2712_PHY_CONFIGURING && bank == BCM2712_PHY_BRIDGE)
        return offset == 0x4304 || offset == 0x184c || offset == 0x1100 ||
            offset == 0x1104 || (!write && offset == 0x1108);
    return 0;
}
#endif
