/* SPDX-License-Identifier: BSD-2-Clause */
#include "BCM2712PCIResourceBridge.h"
#include <IOKit/pci/IOPCIPrivate.h>

static_assert(__is_abstract(BCM2712PCIResourceBridge), "A real mapping/lifecycle owner is mandatory");
static_assert(sizeof(IOPCIPhysicalAddress) == 20, "Original assigned-addresses ABI");
OSDefineMetaClassAndAbstractStructors(BCM2712PCIResourceBridge, BCM2712PCIConfigBridge)

bool BCM2712PCIResourceBridge::init(OSDictionary *properties)
{
    if (!BCM2712PCIConfigBridge::init(properties)) return false;
    resourceState = 0;
    return true;
}

bool BCM2712PCIResourceBridge::bindResourceWindows(const struct rpi5_pcie_fdt *binding)
{
    if (__atomic_load_n(&resourceState, __ATOMIC_RELAXED) || !configAccessHealthy() ||
        !binding || !bcm2712_pci_resource_windows_valid(binding->outbound, binding->outbound_count))
        return false;
    struct rpi5_pcie_window_plan expected;
    if (rpi5_pcie_windows_plan(binding, RPI5_PCIE_WINDOW_ACK_FOUR_BYTES, &expected)) return false;
    const auto &programmed = configAccess->link->windows->plan;
    for (unsigned i = 0; i < 2; i++) {
        const auto &a = expected.outbound[i], &b = programmed.outbound[i];
        if (a.cpu_base != b.cpu_base || a.declared_end != b.declared_end ||
            a.decode_end != b.decode_end || a.pci_base != b.pci_base || a.size != b.size ||
            a.pci_lo != b.pci_lo || a.pci_hi != b.pci_hi || a.base_limit != b.base_limit ||
            a.base_hi != b.base_hi || a.limit_hi != b.limit_hi || a.padding_bytes != b.padding_bytes)
            return false;
    }
    if (!configAccessHealthy()) return false;
    for (unsigned i = 0; i < 2; i++) resourceWindows[i] = binding->outbound[i];
    __atomic_store_n(&resourceState, 1, __ATOMIC_RELEASE);
    return true;
}

bool BCM2712PCIResourceBridge::resourceAccessHealthy(void)
{
    return __atomic_load_n(&resourceState, __ATOMIC_ACQUIRE) == 3 && configAccessHealthy();
}

bool BCM2712PCIResourceBridge::configure(IOService *provider)
{
    UInt32 expected = 1;
    if (!provider || !__atomic_compare_exchange_n(&resourceState, &expected, 2, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    /* These are PCI bus addresses. Never feed CPU addresses to Apple's allocator,
     * or use decode_end (which includes the non-allocatable four-byte excess). */
    bool ok = configAccessHealthy() &&
        addBridgeMemoryRange(resourceWindows[0].pci_base, resourceWindows[0].size, true) &&
        addBridgePrefetchableMemoryRange(resourceWindows[1].pci_base, resourceWindows[1].size) &&
        configAccessHealthy();
    __atomic_store_n(&resourceState, ok ? 3 : 4, __ATOMIC_RELEASE);
    if (!ok) quarantineResourceOwner();
    /* A partial allocator addition is not retried or published after failure. */
    return ok;
}

IOReturn BCM2712PCIResourceBridge::resourceFailure(IOPCIDevice *nub, IOReturn error)
{
    __atomic_store_n(&resourceState, 4, __ATOMIC_RELEASE);
    quarantineResourceOwner();
    /* Original getNubResources sets this marker BEFORE calling this virtual.
     * Do not let a subsequent call mistake a failed addressing attempt for
     * successful resource publication. Owner serializes all such calls. */
    if (nub) nub->removeProperty(kIOPCIResourcedKey);
    return error;
}

IOReturn BCM2712PCIResourceBridge::getDTNubAddressing(IOPCIDevice *nub)
{
    if (!nub || !resourceAccessHealthy()) return resourceFailure(nub, kIOReturnNotReady);
    IOPCIAddressSpace device;
    device.bits = 0;
    device.s.busNum = nub->getBusNumber();
    device.s.deviceNum = nub->getDeviceNumber();
    device.s.functionNum = nub->getFunctionNumber();
    OSObject *property = nub->copyProperty("assigned-addresses");
    OSData *data = OSDynamicCast(OSData, property);
    struct bcm2712_pci_resource_address rows[6];
    uint32_t count = 0;
    bool valid = (!property || data) && bcm2712_pci_resource_addresses(resourceWindows, 2,
        data ? data->getBytesNoCopy() : nullptr, data ? data->getLength() : 0, device, rows, &count);
    if (property) property->release();
    /* RP1 must have assigned BAR1; a missing property is never an empty success.
     * Root bridge may legitimately have no BAR resources. */
    bool bar1 = false;
    for (uint32_t i = 0; valid && i < count; i++) {
        if ((rows[i].tag & 0xff) == kIOPCIConfigBaseAddress1) bar1 = true;
    }
    if (!valid || (device.s.busNum == 1 && !bar1)) return resourceFailure(nub, kIOReturnBadArgument);
    OSObject *existing = nub->copyProperty(gIODeviceMemoryKey);
    if (existing) {
        existing->release();
        /* Original relocation redirects cached descriptors/maps in place. This
         * first-publication layer must not silently replace those live objects. */
        return resourceFailure(nub, kIOReturnUnsupported);
    }
    if (!admitNubMemory(nub, rows, count) || !resourceAccessHealthy())
        return resourceFailure(nub, kIOReturnNotPermitted);
    OSArray *array = OSArray::withCapacity(count ? count : 1);
    if (!array) return resourceFailure(nub, kIOReturnNoMemory);
    for (uint32_t i = 0; i < count; i++) {
        /* Stage a new array, never redirect or mutate an existing live mapping.
         * No map() call here. The original family maps only after success. */
        IOMemoryDescriptor *memory = IOMemoryDescriptor::withAddressRange(rows[i].cpu_base,
            rows[i].size, kIODirectionNone | kIOMemoryMapperNone | kIOMemoryHostOnly |
                (kIOInhibitCache << kIOMemoryBufferCacheShift), nullptr);
        if (!memory) {
            array->release();
            return resourceFailure(nub, kIOReturnNoMemory);
        }
        memory->setTag(rows[i].tag);
        bool added = array->setObject(memory);
        memory->release();
        if (!added) {
            array->release();
            return resourceFailure(nub, kIOReturnNoMemory);
        }
    }
    bool committed = resourceAccessHealthy() && nub->setProperty(gIODeviceMemoryKey, array);
    array->release();
    return committed ? kIOReturnSuccess : resourceFailure(nub, kIOReturnError);
}
