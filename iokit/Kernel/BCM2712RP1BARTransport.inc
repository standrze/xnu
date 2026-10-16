/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct post-ID BAR sizing variant. No command/BME/assignment writes. */
#if !RPI5_PCIE_ID_TRIAL || !RPI5_RP1_CONFIG_DIAGNOSTIC || !RPI5_PCIE_FW_TRANSPORT
#error "RP1 BAR sizing requires the contained single-CPU discovery profile"
#endif
int BCM2712PCIePHYTransport::rp1BarAuthorize(void *context,
    const struct rpi5_pcie_config_request *request)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !self->onOwnerThread() || !self->trialMode || !self->rp1Locked ||
        self->getPhase()!=BCM2712_PHY_RP1_INSPECTING ||
        self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY ||
        !rpi5_rp1_bar1_write_allowed(&self->barProbe,request))return -1;
    return self->guard()?0:-1;
}
int BCM2712PCIePHYTransport::rp1BarWrite(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset==0x9000)return rp1Write(context,offset,width,value);
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    const struct rpi5_pcie_config_request request={1,0,0,0x14,4,1,value};
    if(!self || width!=4 || offset!=0x8014 || rp1BarAuthorize(context,&request))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard()?0:-1;
}
