/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCI_CONFIG_BRIDGE_H
#define BCM2712_PCI_CONFIG_BRIDGE_H
#include <IOKit/pci/IOPCIBridge.h>
#include "../../loader/rpi5/pcie_config.h"

/* Configuration layer over the ORIGINAL IOPCIBridge API, not a stand-in family.
 * Deliberately abstract: a concrete root provider must implement start/configure
 * with genuine mapping/lifecycle/recovery and FDT address-resource integration
 * before invoking original IOPCIBridge::start (which immediately enumerates).
 * No catalogue entry or boot source-list inclusion exists yet.
 * A provider binds once before publication; it owns/drains session/callback and
 * mapping lifetimes until all config clients are detached. No registry property
 * or public boolean is accepted as hardware/DMA admission. */
class BCM2712PCIConfigBridge : public IOPCIBridge {
    OSDeclareAbstractStructors(BCM2712PCIConfigBridge)
protected:
    struct rpi5_pcie_config *configAccess;
    bool bindConfigAccess(struct rpi5_pcie_config *);
    bool configAccessHealthy(void);
private:
    UInt32 configFailure; /* Monotonic atomic latch: original void writes cannot report errors. */
    UInt32 readConfig(IOPCIAddressSpace, UInt8, UInt32);
    void writeConfig(IOPCIAddressSpace, UInt8, UInt32, UInt32);
public:
    bool init(OSDictionary *properties = nullptr) override;
    bool start(IOService *) override = 0;
    bool configure(IOService *) override = 0;
    UInt8 firstBusNum(void) override;
    UInt8 lastBusNum(void) override;
    IODeviceMemory *ioDeviceMemory(void) override;
    IOPCIAddressSpace getBridgeSpace(void) override;
    UInt32 configRead32(IOPCIAddressSpace, UInt8) override;
    UInt16 configRead16(IOPCIAddressSpace, UInt8) override;
    UInt8 configRead8(IOPCIAddressSpace, UInt8) override;
    void configWrite32(IOPCIAddressSpace, UInt8, UInt32) override;
    void configWrite16(IOPCIAddressSpace, UInt8, UInt16) override;
    void configWrite8(IOPCIAddressSpace, UInt8, UInt8) override;
};
#endif
