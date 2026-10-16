/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "BCM2712PCIePHYPolicy.h"

int main(void)
{
    const uint64_t bases[3] = {0x1000120000, 0x1000119500, 0x1001504318};
    const uint64_t lengths[3] = {0x9310, 0x10, 0x30};
    const uint64_t pages[3] = {0x1000120000, 0x1000118000, 0x1001504000};
    const uint64_t sizes[3] = {0xc000, 0x4000, 0x4000};
    struct bcm2712_phy_mapping out, before;
    memset(&out, 0xa5, sizeof out);
    for (unsigned i = 0; i < 3; i++) {
        assert(bcm2712_phy_mapping_plan(i, bases[i], lengths[i], &out));
        assert(out.physical == bases[i] && out.bytes == lengths[i]);
        assert(out.page == pages[i] && out.page_bytes == sizes[i]);
        assert(out.page + out.offset == out.physical);
        assert(out.offset + out.bytes <= out.page_bytes);
        before = out;
        assert(!bcm2712_phy_mapping_plan(i, bases[i] + 4, lengths[i], &out));
        assert(!memcmp(&out, &before, sizeof out));
        assert(!bcm2712_phy_mapping_plan(i, bases[i], lengths[i] - 1, &out));
        assert(!memcmp(&out, &before, sizeof out));
        assert(!bcm2712_phy_mapping_plan(i, bases[i], UINT64_MAX, &out));
        assert(!memcmp(&out, &before, sizeof out));
    }
    before = out;
    assert(!bcm2712_phy_mapping_plan(3, 0, 0, &out));
    assert(!memcmp(&out, &before, sizeof out));
    assert(!bcm2712_phy_mapping_plan(0, bases[0], lengths[0], NULL));
    unsigned accepted = 0;
    for (unsigned phase = 0; phase < 9; phase++)
        for (unsigned bank = 0; bank < 4; bank++)
            for (unsigned write = 0; write < 3; write++)
                for (unsigned width = 0; width <= 8; width++)
                    for (uint32_t offset = 0; offset <= 0xc000; offset++) {
                        int want = 0;
                        if (width == 4 && write <= 1) {
                            if (phase == BCM2712_PHY_RESETTING && bank == BCM2712_PHY_RESET)
                                want = write ? offset == 0x18 || offset == 0x1c : offset == 0x20;
                            if (phase == BCM2712_PHY_CALIBRATING && bank == BCM2712_PHY_RESCAL)
                                want = offset == 0 || (!write && offset == 8);
                            if (phase == BCM2712_PHY_CONFIGURING && bank == BCM2712_PHY_BRIDGE)
                                want = offset == 0x4304 || offset == 0x184c || offset == 0x1100 ||
                                    offset == 0x1104 || (!write && offset == 0x1108);
                        }
                        int got = bcm2712_phy_access_allowed(phase, bank, offset, width, write);
                        assert(got == want);
                        accepted += (unsigned)got;
                    }
    assert(accepted == 15);
    assert(!bcm2712_phy_access_allowed(BCM2712_PHY_CONFIGURING, BCM2712_PHY_BRIDGE, UINT32_MAX, 4, 0));
    puts("PCIE_PHY_POLICY_PASS ACCEPTED_ACCESSES=15 NO_MMIO=1");
    return 0;
}
