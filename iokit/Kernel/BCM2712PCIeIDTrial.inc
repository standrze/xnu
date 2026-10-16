/* SPDX-License-Identifier: BSD-2-Clause */
/* Bounded first-controller/RP1-ID provider. No inbound host-memory decode. */
#if !RPI5_PCIE_ID_TRIAL || !RPI5_RP1_CONFIG_DIAGNOSTIC || !RPI5_PCIE_FW_TRANSPORT
#error "Controller ID trial requires its distinct firmware/RP1 build"
#endif
int BCM2712PCIePHYTransport::trialOwner(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return self && self->trialMode && self->checkingLifecycle && self->onOwnerThread() &&
        ml_get_cpu_count()==1 && __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)==self &&
        self->providerOpened && self->ownerProvider && self->ownerProvider->isOpen(self) &&
        self->maps[0] && self->maps[1] && self->maps[2] ? 0 : -1;
}
int BCM2712PCIePHYTransport::trialRead(void *context,uint32_t offset,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if (!out || trialOwner(context) || (offset&3)) return -1;
    bool allowed=offset==0x4068 || offset==0x4064 || offset==0x4304 || offset==0x4044;
    for(unsigned i=0;i<3;i++) allowed|=offset==0x402c+8*i || offset==0x4030+8*i ||
        offset==0x40ac+8*i || offset==0x40b0+8*i;
    for(unsigned i=0;i<2;i++) allowed|=offset==0x400c+8*i || offset==0x4010+8*i;
    for(unsigned i=0;i<4;i++) allowed|=offset==0x4070+4*i || offset==0x4080+8*i || offset==0x4084+8*i;
    for(unsigned i=0;i<7;i++) allowed|=offset==0x40d4+8*i || offset==0x410c+8*i;
    if (!allowed) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if (trialOwner(context) || value==UINT32_MAX) return -1;
    *out=value;return 0;
}
int BCM2712PCIePHYTransport::trialOrder(void *context)
{
    if (trialOwner(context)) return -1;
    __asm__ volatile("dsb sy" ::: "memory");
    return trialOwner(context);
}
int BCM2712PCIePHYTransport::trialAdmission(IOService *provider,unsigned lifecycle)
{
    auto *self=__atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE);
    if (!self || provider!=self->ownerProvider || trialOwner(self) ||
        lifecycle!=self->lifecyclePhase || lifecycle>BCM2712_CONTROLLER_RELEASED) return -1;
    /* The firmware verifier independently rechecks controller1/RESCAL before
     * and after every post-claim callback. Keep an actual NS reset43 read too;
     * never access controller MMIO while reset44 is being pulsed. */
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t resets=*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_RESET]+0x20);
    __asm__ volatile("dsb sy" ::: "memory");
    if (trialOwner(self) || resets==UINT32_MAX || (resets&0x800)) return -1;
    if (lifecycle==BCM2712_CONTROLLER_INITIALIZING)
        return self->trialPreclaim && self->irqClaimed && self->fwClaimed ? 0 : -1;
    uint32_t status,control,debug;
    if (resets&0x1000 || trialRead(self,0x4068,&status) || trialRead(self,0x4064,&control) ||
        trialRead(self,0x4304,&debug)) return -1;
    if ((status&0xc0)!=0x80 || (control&1) || (debug&0x08000000)) return -1;
    if (lifecycle==BCM2712_CONTROLLER_PRECLAIM) {
        if (self->trialPreclaim || self->claimAttempted || self->getPhase()!=BCM2712_PHY_PREPARED ||
            (status&0x30) || (control&4)) return -1;
        self->trialPreclaim=true;return 0;
    }
    if (!self->trialPreclaim || !self->irqClaimed || !self->fwClaimed) return -1;
    if (lifecycle==BCM2712_CONTROLLER_HELD_RESET) {
        if ((status&0x30) || (control&4)) return -1;
        /* Fresh unused decoders; active1..3 may be disabled by the programmer
         * in this phase, while actual PERST/link-down isolates the endpoint. */
        for(unsigned i=0;i<7;i++) {
            uint32_t value;if (trialRead(self,0x40d4+8*i,&value) || (value&31)) return -1;
        }
        for(unsigned slot=2;slot<4;slot++) {
            uint32_t low,high,limit;
            if(trialRead(self,0x4070+4*slot,&low) || trialRead(self,0x4080+8*slot,&high) ||
                trialRead(self,0x4084+8*slot,&limit)) return -1;
            uint64_t base=((uint64_t)(high&255)<<32)|((uint64_t)(low&0xfff0)<<16);
            uint64_t end=((uint64_t)(limit&255)<<32)|(low&0xfff00000)|0xfffff;
            if(base<=end)return -1;
        }
        return 0;
    }
    /* Ten inbound decoders remain disabled through PERST release, training
     * and config reads. No RP1 DMA/MSI-target mapping is admitted here. */
    uint32_t msi;
    if (trialRead(self,0x4044,&msi) || (msi&1)) return -1;
    for(unsigned i=0;i<3;i++) if(self->windows.plan.inbound[i].bar_lo&31)return -1;
    if(self->trialWindows.state==RPI5_PCIE_RELEASED_EMPTY) {
        const struct rpi5_pcie_released_windows_io io={self,self->binding.bridge_regs.start,
            self->binding.bridge_regs.end-self->binding.bridge_regs.start,trialOwner,trialRead,trialOrder};
        if(rpi5_pcie_released_windows_init(&self->trialWindows,&self->windows,&io))return -1;
    }
    struct rpi5_pcie_released_observation observed;
    return rpi5_pcie_released_windows_check(&self->trialWindows,&observed);
}
bool BCM2712PCIePHYTransport::trialDisableMSI()
{
    if(!trialMode || !onOwnerThread() || getPhase()!=BCM2712_PHY_RC_CONFIGURING ||
        lifecyclePhase!=BCM2712_CONTROLLER_HELD_RESET || !guard())return false;
    __asm__ volatile("dmb osh" ::: "memory");
    volatile uint32_t *reg=reinterpret_cast<volatile uint32_t *>(registers[BCM2712_PHY_BRIDGE]+0x4044);
    uint32_t before=*reg;
    __asm__ volatile("dsb sy" ::: "memory");
    if(before==UINT32_MAX || !guard())return false;
    __asm__ volatile("dmb osh" ::: "memory");
    *reg=before&~UINT32_C(1);
    __asm__ volatile("dsb sy" ::: "memory");
    uint32_t after=*reg;
    __asm__ volatile("dsb sy" ::: "memory");
    return after==(before&~UINT32_C(1)) && guard();
}
bool BCM2712PCIePHYTransport::runBoundedRP1Trial(struct bcm2712_rp1_observation *out)
{
    if(!out || !onOwnerThread() || ml_get_cpu_count()!=1 || trialMode ||
        getPhase()!=BCM2712_PHY_PREPARED)return false;
    trialMode=true;
    const struct bcm2712_controller_admission admission={trialAdmission};
    return runControllerAndObserveRP1(&admission,out);
}
/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching, so no
 * PCIe/RP1 driver can own the pages or enable an endpoint concurrently. The
 * one-CPU profile, retained owner and readback checks remain runtime checks.
 * Always terminal: no shell/driver matching follows a diagnostic mutation. */
extern "C" void rpi5_pcie_id_trial_start(void) __attribute__((noreturn));
extern "C" void rpi5_pcie_id_trial_start(void)
{
    kprintf("RPI5XNU:PCIEID:BEGIN INBOUND_DISABLED\n");
    bool ok=false;
    IOService *provider=new IOService;
    BCM2712PCIePHYTransport *transport=new BCM2712PCIePHYTransport;
    struct bcm2712_rp1_observation observed={};
    bool prepared=provider && transport && provider->init() && transport->init() &&
        transport->prepareBoot(provider);
    kprintf("RPI5XNU:PCIEID:PREPARED OK=%u CPUS=%u\n",(unsigned)prepared,ml_get_cpu_count());
    if(prepared)ok=transport->runBoundedRP1Trial(&observed);
    kprintf("RPI5XNU:PCIEID:END OK=%u PHASE=%u ID=%08x COMMAND=%04x BAR1=%08x GEN=%u LANES=%u\n",
        (unsigned)ok,transport?transport->trialPhase():BCM2712_PHY_EMPTY,
        observed.endpoint.header[0],(unsigned)observed.endpoint.command,
        observed.endpoint.bar1_pci_base,observed.controller.link.generation,observed.controller.link.lanes);
    (void)ml_set_interrupts_enabled(false);
    for(;;)__asm__ volatile("wfi" ::: "memory");
}
