/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCI_CONFIG_ADDRESS_H
#define BCM2712_PCI_CONFIG_ADDRESS_H
#include <IOKit/pci/IOPCIDevice.h>
#include "../../loader/rpi5/pcie_config.h"

/* Use ORIGINAL endian-specific bitfields; phys.hi is NOT an ECAM selector.
 * registerNum is not an additional offset: callers supply the low byte
 * separately and extended register bits in space.es. No hardware access. */
static inline struct rpi5_pcie_config_request
bcm2712_pci_config_request(IOPCIAddressSpace space, UInt8 offset,
    UInt32 width, UInt32 write, UInt32 value)
{
    struct rpi5_pcie_config_request r;
    r.bus = space.s.busNum;
    r.device = space.s.deviceNum;
    r.function = space.s.functionNum;
    r.offset = (space.es.registerNumExtended << 8) | offset;
    r.width = width;
    r.write = write;
    r.value = value;
    return r;
}
#endif
