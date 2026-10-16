/* SPDX-License-Identifier: BSD-2-Clause */
/* Separate copied transport only; never changes the accepted controller. */
#if !RPI5_PCIE_IRQ_TRANSPORT || !RPI5_PCIE_IRQ_MASK || !RPI5_PCIE_CONTROLLER_DIAGNOSTIC
#error "PCIe IRQ transport requires its separate opt-in controller/IRQ build"
#endif
bool BCM2712PCIePHYTransport::claimControllerIRQ(struct rpi5_pcie_irq_observation *out)
{
    if (!out || !onOwnerThread() || !controllerMode || !claimAttempted ||
        getPhase() != BCM2712_PHY_RESETTING || irqClaimed || claimingIRQ || checkingLifecycle ||
        __atomic_load_n(&phyOwner, __ATOMIC_ACQUIRE) != this || !providerOpened ||
        !ownerProvider || !ownerProvider->isOpen(this))
        return false;
    claimingIRQ = true;
    /* Use the real XNU API, including its interrupt-disable accounting and
     * asynchronous-exception state. Do not write DAIF behind the kernel's back.
     * The existing PM lease was claimed ONCE by runInitialPHY before here. */
    bool enabled = ml_set_interrupts_enabled(false);
    if (!pe_rpi5_pcie_irq_claim(this, &binding, out)) {
        /* A partial W1C transaction may have happened. Never restore local
         * interrupts, retry, unmap or touch reset/RESCAL after failed claim.
         * This is terminal diagnostic failure: future admitted boot code must
         * park for the already-owned autonomous watchdog, not resume/sleep. */
        fail();
        return false;
    }
    irqClaimed = true;
    claimingIRQ = false;
    (void)ml_set_interrupts_enabled(enabled);
    /* Restoring interrupts may service an AST/preempt. The first subsequent
     * controller callback must freshly check owner, watchdog AND GIC state. */
    return true;
}

bool BCM2712PCIePHYTransport::guard()
{
    if (!onOwnerThread()) return false; /* Foreign caller cannot mutate owner state. */
    unsigned currentPhase = getPhase();
    if (!claimAttempted ||
        !((currentPhase >= BCM2712_PHY_RESETTING && currentPhase <= BCM2712_PHY_CONFIGURING) ||
          currentPhase == BCM2712_PHY_UBUS_CONFIGURING ||
          currentPhase == BCM2712_PHY_UNUSED_INSPECTING ||
          currentPhase == BCM2712_PHY_QOS_CONFIGURING ||
          currentPhase == BCM2712_PHY_CLOCK_PREPARING ||
          currentPhase == BCM2712_PHY_RC_CONFIGURING ||
          currentPhase == BCM2712_PHY_LINK_TRAINING ||
          currentPhase == BCM2712_PHY_CLOCK_FINISHING) ||
        __atomic_load_n(&phyOwner, __ATOMIC_ACQUIRE) != this || !providerOpened ||
        !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this)) {
        fail();
        return false;
    }
    if (controllerMode) {
        struct rpi5_pcie_irq_observation observed;
        if (checkingLifecycle || claimingIRQ || !irqClaimed || !controllerAdmission.check ||
            !pe_rpi5_pcie_irq_check(this, &observed)) { fail(); return false; }
        checkingLifecycle = true;
        int result = controllerAdmission.check(ownerProvider, lifecyclePhase);
        checkingLifecycle = false;
        /* A provider must not re-enable our SPIs or steal mapping/ownership.
         * Recheck the actual lease after it returns, not a cached MASKED bit. */
        if (result || !onOwnerThread() || getPhase() != currentPhase ||
            __atomic_load_n(&phyOwner, __ATOMIC_ACQUIRE) != this || !providerOpened ||
            !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_pcie_irq_check(this, &observed) ||
            !pe_rpi5_watchdog_check_pcie(this)) {
            fail(); return false;
        }
    }
    return true;
}
