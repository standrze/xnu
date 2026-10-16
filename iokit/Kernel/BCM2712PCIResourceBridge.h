/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCI_RESOURCE_BRIDGE_H
#define BCM2712_PCI_RESOURCE_BRIDGE_H
extern "C" {
#include "../../loader/rpi5/pcie_windows.h"
}
#include "BCM2712PCIConfigBridge.h"
#include "BCM2712PCIResourceAddress.h"

/* Original Apple allocator stays in PCI bus space; only published device
 * descriptors are CPU translated. Still abstract and absent from boot/catalogue.
 * Concrete owner serializes enumeration/relocation and drains all clients before
 * releasing the immutable binding, config session or controller mapping. */
class BCM2712PCIResourceBridge : public BCM2712PCIConfigBridge {
    OSDeclareAbstractStructors(BCM2712PCIResourceBridge)
private:
    struct rpi5_pcie_window resourceWindows[2];
    UInt32 resourceState; /* 0 unbound, 1 bound, 2 configuring, 3 configured, 4 failed. */
    IOReturn getDTNubAddressing(IOPCIDevice *) override;
    IOReturn resourceFailure(IOPCIDevice *, IOReturn);
protected:
    /* Only before publication, with genuine exclusive lifecycle ownership.
     * Must match the same COMPLETE window session used by configAccess. */
    bool bindResourceWindows(const struct rpi5_pcie_fdt *);
    bool resourceAccessHealthy(void);
    /* Required LIVE owner admission, not a registry boolean. Verify identity,
     * assignment/type/size/readback, memory decode and lifetime/fault containment
     * for every descriptor. Original family may immediately map them afterward.
     * Hold that admission until all clients/maps detach; reject unexpected BARs.
     * Does not authorize IRQ/MSI, bus mastering, RAM allocation or DMA. */
    virtual bool admitNubMemory(IOPCIDevice *,
        const struct bcm2712_pci_resource_address *, uint32_t) = 0;
    /* Monotonic LOCAL owner quarantine, bounded, no MMIO/reset/cleanup/retry.
     * Prohibit other direct config/core/resource clients after any failure. */
    virtual void quarantineResourceOwner(void) = 0;
public:
    bool init(OSDictionary *properties = nullptr) override;
    bool start(IOService *) override = 0;
    bool configure(IOService *) override;
};
#endif
