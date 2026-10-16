/* SPDX-License-Identifier: BSD-2-Clause */
/* Original Apple type definitions, no re-declared IOKit types or driver calls. */
#include "../../../iokit/Kernel/BCM2712PCIConfigAddress.h"

extern "C" int main(void);
extern "C" int main(void)
{
    static_assert(sizeof(IOPCIAddressSpace) == 4, "Original PCI address width");
    for (unsigned bus=0; bus<256; bus++) for (unsigned dev=0; dev<32; dev++)
    for (unsigned fn=0; fn<8; fn++) {
        IOPCIAddressSpace space;
        space.bits = (bus<<16) | (dev<<11) | (fn<<8) | 0xa5;
        struct rpi5_pcie_config_request r = bcm2712_pci_config_request(space,0x7c,4,0,0);
        if (r.bus!=bus || r.device!=dev || r.function!=fn || r.offset!=0x7c ||
            r.width!=4 || r.write || r.value) return 1;
    }
    for (unsigned bus=0; bus<2; bus++) for (unsigned offset=0; offset<4096; offset++) {
        IOPCIAddressSpace space;
        space.bits = 0xf0000000 | ((offset>>8)<<24) | (bus<<16) | 0xa5;
        struct rpi5_pcie_config_request r = bcm2712_pci_config_request(space,(UInt8)offset,1,1,0x78);
        if (r.bus!=bus || r.device || r.function || r.offset!=offset ||
            r.width!=1 || r.write!=1 || r.value!=0x78) return 2;
    }
    return 0;
}
