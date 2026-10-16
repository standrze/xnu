/* SPDX-License-Identifier: BSD-2-Clause */
/* This is a real caller, but only private CPU-owned RAM is changed. No queue
 * address, BME, inbound enable, DMA/IRQ activation or packet operation exists. */
bool BCM2712PCIePHYTransport::prepareCPUOwnedRings()
{
    /* Called by the unique before-matching IOStartIOKit path, before any PM,
     * IRQ or firmware lease. That caller holds no WorkLoop command gate.
     * Genuine IOBuffer/IODMA allocation and prepare may sleep only here. */
    if(dmaPreparePhase==1) { dmaPreparePhase=3;return false; }
    if(dmaPreparePhase || dmaMemory || !onOwnerThread() || ml_get_cpu_count()!=1 ||
        claimAttempted || irqClaimed || fwClaimed || trialMode ||
        getPhase()!=BCM2712_PHY_PREPARED || !providerOpened || !ownerProvider)return false;
    dmaPreparePhase=1;
    IOService *provider=ownerProvider;
    auto active=[&]() {return dmaPreparePhase==1 && onOwnerThread() &&
        getPhase()==BCM2712_PHY_PREPARED && providerOpened && ownerProvider==provider &&
        !claimAttempted && !irqClaimed && !fwClaimed && !trialMode;};
    if(!provider->isOpen(this) || !active()) { dmaPreparePhase=3;return false; }
    dmaMemory=new BCM2712GEMDMABatch;
    if(!dmaMemory || !active()) { dmaPreparePhase=3;return false; }
    bool prepared=dmaMemory->prepare();
    if(!prepared || !active()) { dmaPreparePhase=3;return false; }
    dmaPreparePhase=2;return true;
}
int BCM2712PCIePHYTransport::dmaRingSource() const
{
    if(!dmaMemory || !dmaRingActive || dmaRingRevoked || !onOwnerThread() || checkingLifecycle ||
        getPhase()!=BCM2712_PHY_RP1_INSPECTING || lifecyclePhase!=BCM2712_CONTROLLER_RELEASED ||
        capabilitySession.self!=&capabilitySession || capabilitySession.identity!=&gemSession ||
        capabilitySession.state!=RPI5_GEM_CAP_COMPLETE || capabilitySession.reads!=16 ||
        capabilitySession.busy || capabilitySession.pending ||
        gemSession.stage!=RPI5_GEM_COMPLETE || gemSession.reads!=32 || gemSession.pending ||
        !gemSession.clocks_ready || trialWindows.state!=RPI5_PCIE_RELEASED_READY ||
        trialWindows.windows!=&windows || windows.state!=RPI5_PCIE_WINDOWS_COMPLETE)return -1;
    for(unsigned i=0;i<3;i++)if(windows.plan.inbound[i].bar_lo&31)return -1;
    return gemSource(const_cast<BCM2712PCIePHYTransport *>(this),&gemSession,&decodeCycle);
}
int BCM2712PCIePHYTransport::dmaRingCurrent(void *context,const BCM2712GEMDMABatch *memory,
    const struct rpi5_gem_cap_session *cap,uint64_t *now)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || memory!=self->dmaMemory || cap!=&self->capabilitySession || !now ||
        self->dmaRingSource() || !self->guard() || self->dmaRingSource())return -1;
    /* Actual existing guard contains both fresh firmware checks and the full
     * independent90-read disabled-window/lifecycle check. Read time LAST;
     * no cached lease or timestamp from before that verification is returned. */
    uint64_t ticks,ns;
    clock_get_uptime(&ticks);absolutetime_to_nanoseconds(ticks,&ns);
    if(self->dmaRingSource())return -1;
    *now=ns/1000;return 0;
}
bool BCM2712PCIePHYTransport::stagePreparedCPUOwnedRings()
{
    if(dmaRingActive) { dmaRingRevoked=true;return false; }
    if(dmaRingAttempted || dmaRingActive || !dmaMemory ||
        dmaMemory->state()!=BCM2712GEMDMABatch::Held || !onOwnerThread())return false;
    dmaRingAttempted=true;dmaRingActive=true;
    uint64_t ticks,ns;
    clock_get_uptime(&ticks);absolutetime_to_nanoseconds(ticks,&ns);
    uint64_t start=ns/1000;
    if(!start || start>UINT64_MAX-BCM2712GEMDMABatch::StageMaximumUS || dmaRingSource())return false;
    dmaLive={this,this,&capabilitySession,start,start,start+BCM2712GEMDMABatch::StageMaximumUS,dmaRingCurrent};
    /* The provider independently checks the exact immutable source objects,
     * actual retained Normal-NC mappings and every64-byte batch boundary.
     * Local observation publishes only after all CPU-owned readbacks match. */
    if(!dmaMemory->stageCPUOwned(&dmaLive,&dmaRingsObserved) || dmaRingSource())return false;
    dmaRingActive=false;return true;
}
