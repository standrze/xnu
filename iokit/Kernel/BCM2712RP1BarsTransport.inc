/* SPDX-License-Identifier: BSD-2-Clause */
/* Full BAR inventory before any later endpoint memory-enable operation. */
#if !RPI5_PCIE_ID_TRIAL || !RPI5_RP1_CONFIG_DIAGNOSTIC || !RPI5_PCIE_FW_TRANSPORT
#error "RP1 BAR inventory requires the contained single-CPU discovery profile"
#endif
int BCM2712PCIePHYTransport::rp1BarsAuthorize(void *context,
    const struct rpi5_pcie_config_request *request)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !self->onOwnerThread() || !self->trialMode || !self->rp1Locked ||
        self->getPhase()!=BCM2712_PHY_RP1_INSPECTING ||
        self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY ||
        !rpi5_rp1_bars_write_allowed(&self->barsProbe,request))return -1;
    return self->guard()?0:-1;
}
int BCM2712PCIePHYTransport::rp1BarsWrite(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset==0x9000)return rp1Write(context,offset,width,value);
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(offset<0x8010 || offset>0x8024 || (offset&3) || width!=4)return -1;
    const struct rpi5_pcie_config_request request={1,0,0,offset-0x8000,4,1,value};
    if(!self || rp1BarsAuthorize(context,&request))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard()?0:-1;
}
