/* SPDX-License-Identifier: BSD-2-Clause */
#include "BCM2712PCIConfigBridge.h"
#include "BCM2712PCIConfigAddress.h"

static_assert(__is_abstract(BCM2712PCIConfigBridge), "Provider admission must not be inherited away");

OSDefineMetaClassAndAbstractStructors(BCM2712PCIConfigBridge, IOPCIBridge)

bool BCM2712PCIConfigBridge::init(OSDictionary *properties)
{
    if (!IOPCIBridge::init(properties)) return false;
    configAccess = nullptr;
    configFailure = 0;
    return true;
}

bool BCM2712PCIConfigBridge::bindConfigAccess(struct rpi5_pcie_config *access)
{
    if (configAccess || !rpi5_pcie_config_ready(access)) return false;
    configAccess = access;
    return true;
}

bool BCM2712PCIConfigBridge::configAccessHealthy(void)
{
    return !__atomic_load_n(&configFailure, __ATOMIC_RELAXED) &&
        rpi5_pcie_config_ready(configAccess) != 0;
}

UInt8 BCM2712PCIConfigBridge::firstBusNum(void) { return 0; }
UInt8 BCM2712PCIConfigBridge::lastBusNum(void) { return 1; }
IODeviceMemory *BCM2712PCIConfigBridge::ioDeviceMemory(void) { return nullptr; } /* No PCI I/O aperture. */
IOPCIAddressSpace BCM2712PCIConfigBridge::getBridgeSpace(void)
{
    IOPCIAddressSpace space;
    space.bits = 0;
    return space;
}

UInt32 BCM2712PCIConfigBridge::readConfig(IOPCIAddressSpace space, UInt8 offset, UInt32 width)
{
    if (__atomic_load_n(&configFailure, __ATOMIC_RELAXED)) return UINT32_MAX;
    const struct rpi5_pcie_config_request r = bcm2712_pci_config_request(space, offset, width, 0, 0);
    uint32_t value;
    int rc = rpi5_pcie_config_transfer(configAccess, &r, &value);
    if (rc) {
        if (rc != RPI5_PCIE_CONFIG_ABSENT) __atomic_store_n(&configFailure, 1, __ATOMIC_RELAXED);
        return UINT32_MAX;
    }
    return value;
}

void BCM2712PCIConfigBridge::writeConfig(IOPCIAddressSpace space, UInt8 offset,
    UInt32 width, UInt32 value)
{
    if (__atomic_load_n(&configFailure, __ATOMIC_RELAXED)) return;
    const struct rpi5_pcie_config_request r = bcm2712_pci_config_request(space, offset, width, 1, value);
    /* Original virtual writes have no result. Any admitted transaction failure
     * latches the core's quarantine; concrete start/clients must check health,
     * never interpret a silent void return as successful BAR/DMA admission. */
    int rc = rpi5_pcie_config_transfer(configAccess, &r, nullptr);
    if (rc && rc != RPI5_PCIE_CONFIG_ABSENT) __atomic_store_n(&configFailure, 1, __ATOMIC_RELAXED);
}

UInt32 BCM2712PCIConfigBridge::configRead32(IOPCIAddressSpace s, UInt8 o) { return readConfig(s, o, 4); }
UInt16 BCM2712PCIConfigBridge::configRead16(IOPCIAddressSpace s, UInt8 o) { return (UInt16)readConfig(s, o, 2); }
UInt8 BCM2712PCIConfigBridge::configRead8(IOPCIAddressSpace s, UInt8 o) { return (UInt8)readConfig(s, o, 1); }
void BCM2712PCIConfigBridge::configWrite32(IOPCIAddressSpace s, UInt8 o, UInt32 v) { writeConfig(s, o, 4, v); }
void BCM2712PCIConfigBridge::configWrite16(IOPCIAddressSpace s, UInt8 o, UInt16 v) { writeConfig(s, o, 2, v); }
void BCM2712PCIConfigBridge::configWrite8(IOPCIAddressSpace s, UInt8 o, UInt8 v) { writeConfig(s, o, 1, v); }
