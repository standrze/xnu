/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_PCIE_PHY_DIAGNOSTIC
#error "PCIe PHY transport requires an opt-in BCM2712 DEVELOPMENT build"
#endif
#include "BCM2712PCIePHYTransport.h"
#include <IOKit/IOLib.h>
#include <machine/machine_routines.h>
#include <kern/clock.h>
#include <kern/thread.h>

/* Real built-in private ABI, hidden from the IOKit header view. Exact existing
 * declaration: osfmk/mach/arm/vm_param.h; definition: osfmk/arm/arm_init.c.
 * No implementation/shim is supplied here; linkage checks the actual kernel. */
extern "C" unsigned rpi5_physical_memory_type(uint64_t start, uint64_t end);

OSDefineMetaClassAndStructors(BCM2712PCIePHYTransport, IOService)
static BCM2712PCIePHYTransport *phyOwner;

bool BCM2712PCIePHYTransport::onOwnerThread() const
{
    return !ml_at_interrupt_context() && ownerThread == current_thread();
}
int BCM2712PCIePHYTransport::fail()
{
    /* Only the owner thread mutates session state. No cleanup MMIO, lease
     * release or reset on an error, even if an earlier write took effect. */
    setPhase(BCM2712_PHY_FAILED);
    reset.state = RPI5_PCIE_RESET_QUARANTINED;
    calibration.state = RPI5_PCIE_RESCAL_QUARANTINED;
    serdes.state = RPI5_PCIE_SERDES_QUARANTINED;
    serdes.mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
    return -1;
}
bool BCM2712PCIePHYTransport::guard()
{
    if (!onOwnerThread()) return false; /* Foreign caller cannot mutate owner state. */
    unsigned currentPhase = getPhase();
    if (!claimAttempted || currentPhase < BCM2712_PHY_RESETTING || currentPhase > BCM2712_PHY_CONFIGURING ||
        __atomic_load_n(&phyOwner, __ATOMIC_ACQUIRE) != this || !providerOpened ||
        !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this)) {
        fail();
        return false;
    }
    return true;
}
bool BCM2712PCIePHYTransport::mapBanks()
{
    const struct rpi5_range banks[3] = {binding.bridge_regs, binding.rescal_regs, binding.bridge_reset_regs};
    for (unsigned i = 0; i < 3; i++) {
        struct bcm2712_phy_mapping plan;
        if (!bcm2712_phy_mapping_plan(i, banks[i].start, banks[i].end - banks[i].start, &plan)) return false;
        /* The immutable loader memory-type contract must cover EVERY rounded
         * page as Device. A numeric FDT range alone cannot admit pmap access.
         * This does not prove that the physical block is powered or clocked. */
        if (rpi5_physical_memory_type(plan.page, plan.page + plan.page_bytes) != 2) return false;
        IOMemoryDescriptor *memory = IOMemoryDescriptor::withAddressRange(plan.page, plan.page_bytes,
            kIODirectionNone | kIOMemoryMapperNone | kIOMemoryHostOnly |
                (kIOInhibitCache << kIOMemoryBufferCacheShift), nullptr);
        if (!memory) return false;
        maps[i] = memory->map(kIOMapAnywhere | kIOMapInhibitCache);
        memory->release(); /* Map retains the real descriptor. */
        if (!maps[i] || !maps[i]->getVirtualAddress() || maps[i]->getLength() != plan.page_bytes ||
            (maps[i]->getVirtualAddress() & 0x3fff)) return false;
        registers[i] = maps[i]->getVirtualAddress() + plan.offset;
    }
    return true;
}
bool BCM2712PCIePHYTransport::prepare(IOService *provider, const void *fdt, size_t bytes)
{
    if (ml_at_interrupt_context()) return false;
    unsigned expectedPhase = BCM2712_PHY_EMPTY;
    if (!__atomic_compare_exchange_n(&phase, &expectedPhase, BCM2712_PHY_FAILED, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    ownerThread = current_thread();
    /* A failed preparation cannot recycle this instance. */
    if (!provider || rpi5_fdt_pcie_rp1(fdt, bytes, &binding)) return false;
    BCM2712PCIePHYTransport *expected = nullptr;
    if (!__atomic_compare_exchange_n(&phyOwner, &expected, this, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    singletonHeld = true;
    ownerProvider = provider;
    ownerProvider->retain();
    if (provider->isOpen() || !provider->open(this)) return false;
    providerOpened = true;
    if (!mapBanks()) return false;
    setPhase(BCM2712_PHY_PREPARED);
    return true;
}
void BCM2712PCIePHYTransport::free()
{
    /* runInitialPHY pins this object BEFORE attempting the irreversible claim.
     * A normal reference release can never unmap in-flight diagnostic access. */
    assert(!claimAttempted);
    for (unsigned i = 0; i < 3; i++) if (maps[i]) maps[i]->release();
    if (providerOpened) ownerProvider->close(this);
    if (ownerProvider) ownerProvider->release();
    if (singletonHeld) {
        BCM2712PCIePHYTransport *expected = this;
        bool released = __atomic_compare_exchange_n(&phyOwner, &expected, nullptr, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
        assert(released);
    }
    IOService::free();
}
int BCM2712PCIePHYTransport::read32(unsigned bank, uint32_t offset, uint32_t *out)
{
    if (!onOwnerThread()) return -1;
    if (!out || !bcm2712_phy_access_allowed(getPhase(), bank, offset, 4, 0)) return fail();
    if (!guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value = *reinterpret_cast<volatile uint32_t *>(registers[bank] + offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if (!guard()) return -1;
    *out = value;
    return 0;
}
int BCM2712PCIePHYTransport::write32(unsigned bank, uint32_t offset, uint32_t value)
{
    if (!onOwnerThread()) return -1;
    if (!bcm2712_phy_access_allowed(getPhase(), bank, offset, 4, 1)) return fail();
    /* Reset SET/CLEAR must NEVER touch other controllers' bits. */
    if (bank == BCM2712_PHY_RESET && value != 0x1000) return fail();
    if (!guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(registers[bank] + offset) = value;
    __asm__ volatile("dsb sy" ::: "memory");
    return guard() ? 0 : -1;
}
int BCM2712PCIePHYTransport::resetStatus(void *p, uint32_t *out)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->read32(BCM2712_PHY_RESET, 0x20, out); }
int BCM2712PCIePHYTransport::resetAssert(void *p)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->write32(BCM2712_PHY_RESET, 0x18, 0x1000); }
int BCM2712PCIePHYTransport::resetRelease(void *p)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->write32(BCM2712_PHY_RESET, 0x1c, 0x1000); }
int BCM2712PCIePHYTransport::rescalClaim(void *p)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    /* Singleton retained across all three phases, not released after RESCAL.
     * This does not establish controller 1 power/clock accessibility. */
    if (self->getPhase() != BCM2712_PHY_CALIBRATING || self->reset.state != RPI5_PCIE_RESET_COMPLETE)
        return self->fail();
    return self->guard() ? 0 : -1;
}
int BCM2712PCIePHYTransport::rescalReadStart(void *p, uint32_t *out)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->read32(BCM2712_PHY_RESCAL, 0, out); }
int BCM2712PCIePHYTransport::rescalWriteStart(void *p, uint32_t value)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->write32(BCM2712_PHY_RESCAL, 0, value); }
int BCM2712PCIePHYTransport::rescalReadStatus(void *p, uint32_t *out)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->read32(BCM2712_PHY_RESCAL, 8, out); }
int BCM2712PCIePHYTransport::bridgeRead(void *p, uint32_t offset, uint32_t *out)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->read32(BCM2712_PHY_BRIDGE, offset, out); }
int BCM2712PCIePHYTransport::bridgeWrite(void *p, uint32_t offset, uint32_t value)
{ return static_cast<BCM2712PCIePHYTransport *>(p)->write32(BCM2712_PHY_BRIDGE, offset, value); }
int BCM2712PCIePHYTransport::order(void *p)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->guard()) return -1;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard() ? 0 : -1;
}
int BCM2712PCIePHYTransport::nowUS(void *p, uint64_t *out)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (!out) return self->fail();
    if (!self->guard()) return -1;
    uint64_t time, ns;
    clock_get_uptime(&time);
    absolutetime_to_nanoseconds(time, &ns);
    if (!self->guard()) return -1;
    *out = ns / 1000;
    return 0;
}
int BCM2712PCIePHYTransport::delayUS(void *p, uint32_t us)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (!us || us > 100) return self->fail();
    if (!self->guard()) return -1;
    IODelay(us);
    return self->guard() ? 0 : -1;
}
bool BCM2712PCIePHYTransport::runInitialPHY(struct bcm2712_phy_observation *out)
{
    if (getPhase() != BCM2712_PHY_PREPARED || !onOwnerThread() || !out) return false;
    /* Do not introduce another recovery-permission boolean. The future boot
     * integration must close the documented admission BEFORE calling here. */
    retain();
    claimAttempted = true;
    setPhase(BCM2712_PHY_RESETTING);
    struct bcm2712_phy_observation result = {};
    if (!pe_rpi5_watchdog_claim_pcie(this, &result.watchdog)) { fail(); return false; }
    struct rpi5_pcie_reset_io resetIO = {this, binding.bridge_reset_regs.start,
        binding.bridge_reset_regs.end - binding.bridge_reset_regs.start,
        resetStatus, resetAssert, resetRelease, order, delayUS};
    struct rpi5_pcie_rescal_io calibrationIO = {this, binding.rescal_regs.start,
        binding.rescal_regs.end - binding.rescal_regs.start,
        rescalClaim, rescalReadStart, rescalWriteStart, rescalReadStatus, order, nowUS, delayUS};
    struct rpi5_pcie_mdio_io bridgeIO = {this, binding.bridge_regs.start,
        binding.bridge_regs.end - binding.bridge_regs.start,
        bridgeRead, bridgeWrite, order, nowUS, delayUS};
    if (rpi5_pcie_reset_init(&reset, &binding, &resetIO) || rpi5_pcie_reset_pulse(&reset, &result.reset)) {
        fail(); return false;
    }
    setPhase(BCM2712_PHY_CALIBRATING);
    if (rpi5_pcie_rescal_init(&calibration, &binding, &calibrationIO) ||
        rpi5_pcie_rescal_calibrate(&calibration, &result.calibration)) { fail(); return false; }
    setPhase(BCM2712_PHY_CONFIGURING);
    if (rpi5_pcie_serdes_init(&serdes, &binding, &bridgeIO, &calibration, &reset) ||
        rpi5_pcie_serdes_configure54(&serdes, &result.serdes) || !guard()) { fail(); return false; }
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
