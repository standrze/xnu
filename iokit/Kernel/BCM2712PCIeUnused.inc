/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_UNUSED_DIAGNOSTIC
#error "Unused-window inspection requires its separate diagnostic build"
#endif
int BCM2712PCIePHYTransport::unusedOwner(void *p)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    return self->guard() ? 0 : -1;
}
bool BCM2712PCIePHYTransport::runPHYUBUSAndWindowCheck(struct bcm2712_unused_observation *out)
{
    if (!out || !onOwnerThread() || getPhase() != BCM2712_PHY_PREPARED) return false;
    struct bcm2712_unused_observation result = {};
    /* The existing initial chain performs its documented reset/PHY/UBUS
     * writes. Only the new inspection stage below is read-only. */
    if (!runPHYAndUBUS(&result.ubus)) return false;
    setPhase(BCM2712_PHY_UNUSED_INSPECTING);
    struct rpi5_pcie_unused_io io = {this, binding.bridge_regs.start,
        binding.bridge_regs.end - binding.bridge_regs.start, unusedOwner, bridgeRead};
    if (!guard() || rpi5_pcie_unused_init(&unused, &ubus, &io) ||
        rpi5_pcie_unused_inspect(&unused, &result.unused) || !guard()) {
        fail();
        return false;
    }
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
