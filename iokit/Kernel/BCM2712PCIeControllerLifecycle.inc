/* SPDX-License-Identifier: BSD-2-Clause */
int BCM2712PCIePHYTransport::controllerQuiescent(void *p)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (self->lifecyclePhase != BCM2712_CONTROLLER_HELD_RESET || !self->guard()) return self->fail();
    /* FRESH actual read-only inspection at every window/RC/pre-release check.
     * Never reuse a previous COMPLETE observation as current permission. The
     * provider callback in guard independently retains the rest of the power/
     * clock/shared/IRQ/endpoint/DMA/recovery lifecycle contract throughout. */
    struct rpi5_pcie_unused fresh = {};
    struct rpi5_pcie_unused_observation observation = {};
    struct rpi5_pcie_unused_io io = {self, self->binding.bridge_regs.start,
        self->binding.bridge_regs.end - self->binding.bridge_regs.start, unusedOwner, bridgeRead};
    if (rpi5_pcie_unused_init(&fresh, &self->ubus, &io) ||
        rpi5_pcie_unused_inspect(&fresh, &observation) || !self->guard()) return self->fail();
    self->freshUnusedChecks++;
    return 0;
}
int BCM2712PCIePHYTransport::controllerLifecycle(void *p, unsigned released)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (released > 1 || self->lifecyclePhase != (released ? BCM2712_CONTROLLER_RELEASED :
        BCM2712_CONTROLLER_HELD_RESET)) return self->fail();
    /* After PERST release do NOT require link-down/asserted reset. The
     * independent provider must continue verifying unused-window safety and
     * endpoint/interrupt/DMA quiescence without attempting enumeration. */
    return released ? (self->guard() ? 0 : -1) : controllerQuiescent(p);
}
