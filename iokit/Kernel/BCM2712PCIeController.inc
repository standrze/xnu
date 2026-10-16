/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_CONTROLLER_DIAGNOSTIC
#error "PCIe controller composition requires its separate diagnostic build"
#endif
int BCM2712PCIePHYTransport::controllerRead16(void *p, uint32_t offset, uint16_t *out)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (!out || !bcm2712_controller_access_allowed(self->getPhase(), BCM2712_PHY_BRIDGE, offset, 2, 0))
        return self->fail();
    if (!self->guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint16_t value = *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if (!self->guard()) return -1;
    *out = value;
    return 0;
}
int BCM2712PCIePHYTransport::controllerWrite16(void *p, uint32_t offset, uint16_t value)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (!bcm2712_controller_access_allowed(self->getPhase(), BCM2712_PHY_BRIDGE, offset, 2, 1))
        return self->fail();
    if (!self->guard()) return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard() ? 0 : -1;
}
#include "BCM2712PCIeControllerLifecycle.inc"
#include "BCM2712PCIeControllerRun.inc"
