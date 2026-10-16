/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_PCIE_PHY_TRANSPORT_H
#define BCM2712_PCIE_PHY_TRANSPORT_H
#include <IOKit/IOService.h>
#include <IOKit/IOMemoryDescriptor.h>
#include "BCM2712PCIePHYPolicy.h"
extern "C" {
#include "../../loader/rpi5/pcie_serdes.h"
#include "../../pexpert/arm/rpi5_pcie_watchdog_api.h"
}

struct bcm2712_phy_observation {
    struct rpi5_pcie_watchdog_observation watchdog;
    struct rpi5_pcie_reset_observation reset;
    struct rpi5_pcie_rescal_observation calibration;
    struct rpi5_pcie_serdes_observation serdes;
};

/* Actual Device mapping/volatile-MMIO implementation for the first three
 * initial bring-up cores. Not a registered PCI bridge or runtime NIC driver.
 * Absent from source lists/catalogue; no current boot caller exists.
 *
 * FUTURE CALLER PRECONDITIONS: independently admitted bounded reset AND SSD
 * return, accessible retained firmware power/clocks (including controller 1's
 * shared RESCAL domain), RP1/config/DMA quiesced, exclusive whole-controller
 * ownership and no other consumer of these pages. Opening a nub and this
 * singleton prevent competing instances here, not arbitrary physical users.
 * There is deliberately no registry boolean claiming those conditions.
 *
 * One preparing thread owns every call. No workloop/event sources, public
 * raw-register interface, config/BAR/IRQ/DMA API, retry or power-off operation.
 * After attempting the irreversible watchdog claim the object self-retains
 * and keeps its provider/maps until reset, INCLUDING on failure. Hung/aborting
 * MMIO cannot return an error; autonomous watchdog recovery needs board proof.
 */
class BCM2712PCIePHYTransport : public IOService {
    OSDeclareDefaultStructors(BCM2712PCIePHYTransport)
private:
    IOService *ownerProvider = nullptr;
    void *ownerThread = nullptr;
    IOMemoryMap *maps[3] = {};
    vm_offset_t registers[3] = {};
    struct rpi5_pcie_fdt binding = {};
    struct rpi5_pcie_reset reset = {};
    struct rpi5_pcie_rescal calibration = {};
    struct rpi5_pcie_serdes serdes = {};
    unsigned phase = BCM2712_PHY_EMPTY;
    bool providerOpened = false, singletonHeld = false, claimAttempted = false;
    unsigned getPhase() const { return __atomic_load_n(&phase, __ATOMIC_ACQUIRE); }
    void setPhase(unsigned value) { __atomic_store_n(&phase, value, __ATOMIC_RELEASE); }
    bool onOwnerThread() const;
    bool guard();
    int fail();
    bool mapBanks();
    int read32(unsigned, uint32_t, uint32_t *);
    int write32(unsigned, uint32_t, uint32_t);
    static int resetStatus(void *, uint32_t *);
    static int resetAssert(void *);
    static int resetRelease(void *);
    static int rescalClaim(void *);
    static int rescalReadStart(void *, uint32_t *);
    static int rescalWriteStart(void *, uint32_t);
    static int rescalReadStatus(void *, uint32_t *);
    static int bridgeRead(void *, uint32_t, uint32_t *);
    static int bridgeWrite(void *, uint32_t, uint32_t);
    static int order(void *);
    static int nowUS(void *, uint64_t *);
    static int delayUS(void *, uint32_t);
protected:
    void free() override;
public:
    /* Stable readable raw FDT is decoded with the actual strict decoder. New
     * instance only; no hardware register read/write or PM claim at prepare.
     * Caller's normal release cleans up only PRE-claim preparation failures. */
    bool prepare(IOService *, const void *fdt, size_t bytes);
    /* One watchdog claim, reset44 -> shared RESCAL -> fixed 54-MHz SerDes.
     * Independent output is committed only after every stage/guard passes.
     * Success is PHY sequence only, NOT link training or RP1 discovery. */
    bool runInitialPHY(struct bcm2712_phy_observation *);
};
#endif
