/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_RP1_CONFIG_DIAGNOSTIC || !RPI5_PCIE_FW_TRANSPORT
#error "RP1 observation requires its separate controller/firmware build"
#endif
int BCM2712PCIePHYTransport::rp1Acquire(void *context)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(context);
    if (!self->onOwnerThread() || self->rp1Locked ||
        self->getPhase() != BCM2712_PHY_RP1_INSPECTING) return -1;
    self->rp1Locked = true;
    return 0;
}
void BCM2712PCIePHYTransport::rp1Release(void *context)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(context);
    assert(self->onOwnerThread() && self->rp1Locked);
    self->rp1Locked = false;
}
int BCM2712PCIePHYTransport::rp1Lifecycle(void *context)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(context);
    if (!self->onOwnerThread() || !self->rp1Locked ||
        self->getPhase() != BCM2712_PHY_RP1_INSPECTING) return -1;
    return self->guard() ? 0 : -1;
}
int BCM2712PCIePHYTransport::rp1DenyWrite(void *, const struct rpi5_pcie_config_request *)
{
    return -1;
}
int BCM2712PCIePHYTransport::rp1Read(void *context, uint32_t offset, uint32_t width, uint32_t *out)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(context);
    if (!self->onOwnerThread()) return -1;
    if (!out || !self->rp1Locked || self->getPhase() != BCM2712_PHY_RP1_INSPECTING ||
        !bcm2712_rp1_config_access(offset,width,0)) return self->fail();
    if (!self->guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value = *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if (!self->guard()) return -1;
    *out = value;
    return 0;
}
int BCM2712PCIePHYTransport::rp1Write(void *context, uint32_t offset, uint32_t width, uint32_t value)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(context);
    if (!self->onOwnerThread()) return -1;
    if (!self->rp1Locked || self->getPhase() != BCM2712_PHY_RP1_INSPECTING ||
        !bcm2712_rp1_config_access(offset,width,1) || value != 0x00100000) return self->fail();
    if (!self->guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard() ? 0 : -1;
}
bool BCM2712PCIePHYTransport::runControllerAndObserveRP1(
    const struct bcm2712_controller_admission *admission, struct bcm2712_rp1_observation *out)
{
    if (!out || !onOwnerThread() || rp1Attempted || rp1Locked ||
        getPhase() != BCM2712_PHY_PREPARED) return false;
    rp1Attempted = true;
    struct bcm2712_rp1_observation result = {};
    if (!runController(admission,&result.controller)) return false;
    setPhase(BCM2712_PHY_RP1_INSPECTING);
    struct rpi5_pcie_config_io io = {this,rp1Acquire,rp1Release,rp1Lifecycle,
        rp1DenyWrite,rp1Read,rp1Write,order};
    if (!guard() || rpi5_pcie_config_init(&rp1Config,&link,&io) ||
        rpi5_rp1_config_snapshot(&rp1Config,&result.endpoint) || !guard()) {
        rp1Config.state = RPI5_PCIE_CONFIG_QUARANTINED;
        fail(); return false;
    }
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
