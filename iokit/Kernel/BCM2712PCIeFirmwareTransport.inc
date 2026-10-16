/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_FW_CLIENT || !RPI5_PCIE_FW_TRANSPORT || !RPI5_PCIE_IRQ_TRANSPORT
#error "PCIe firmware transport requires its separate PM/IRQ/firmware build"
#endif
bool BCM2712PCIePHYTransport::claimControllerFirmware(struct rpi5_fw_observation *out)
{
    if(!out || !onOwnerThread() || !controllerMode || !claimAttempted || !irqClaimed ||
        getPhase()!=BCM2712_PHY_RESETTING || fwClaimed || claimingFW || claimingIRQ || checkingLifecycle ||
        __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=this || !providerOpened ||
        !ownerProvider || !ownerProvider->isOpen(this))return false;
    claimingFW=true;
    bool enabled=ml_set_interrupts_enabled(false);
    if(!pe_rpi5_pcie_fw_claim(this,out)){fail();return false;} /* Terminal: keep interrupts masked. */
    fwClaimed=true;claimingFW=false;
    (void)ml_set_interrupts_enabled(enabled);return true;
}
bool BCM2712PCIePHYTransport::guard()
{
    if(!onOwnerThread())return false;
    unsigned currentPhase=getPhase();
    if(!claimAttempted ||
        !((currentPhase>=BCM2712_PHY_RESETTING && currentPhase<=BCM2712_PHY_CONFIGURING) ||
          currentPhase==BCM2712_PHY_UBUS_CONFIGURING || currentPhase==BCM2712_PHY_UNUSED_INSPECTING ||
          currentPhase==BCM2712_PHY_QOS_CONFIGURING || currentPhase==BCM2712_PHY_CLOCK_PREPARING ||
          currentPhase==BCM2712_PHY_RC_CONFIGURING || currentPhase==BCM2712_PHY_LINK_TRAINING ||
          currentPhase==BCM2712_PHY_CLOCK_FINISHING) ||
        __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=this || !providerOpened ||
        !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this)){fail();return false;}
    if(controllerMode){
        struct rpi5_pcie_irq_observation irq;
        struct rpi5_fw_observation fw;
        if(checkingLifecycle || claimingIRQ || claimingFW || !irqClaimed || !fwClaimed || !controllerAdmission.check ||
            !pe_rpi5_pcie_irq_check(this,&irq) || !pe_rpi5_pcie_fw_check(this,&fw)){fail();return false;}
        checkingLifecycle=true;
        int result=controllerAdmission.check(ownerProvider,lifecyclePhase);
        checkingLifecycle=false;
        if(result || !onOwnerThread() || getPhase()!=currentPhase ||
            __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=this || !providerOpened ||
            !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_pcie_fw_check(this,&fw) ||
            !pe_rpi5_pcie_irq_check(this,&irq) || !pe_rpi5_watchdog_check_pcie(this)){fail();return false;}
    }
    return true;
}
