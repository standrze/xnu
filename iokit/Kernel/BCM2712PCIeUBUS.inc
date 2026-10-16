/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_UBUS_DIAGNOSTIC
#error "PCIe UBUS continuation requires its separate diagnostic build"
#endif

bool BCM2712PCIePHYTransport::runPHYAndUBUS(struct bcm2712_ubus_observation *out)
{
    if (!out || !onOwnerThread() || getPhase() != BCM2712_PHY_PREPARED) return false;
    struct bcm2712_ubus_observation result = {};
    /* Use the actual owned reset/calibration/SerDes sessions. This method does
     * not manufacture COMPLETE prerequisites or take a second watchdog lease.
     * The original method pins all ownership before its single claim attempt. */
    if (!runInitialPHY(&result.phy)) return false;
    setPhase(BCM2712_PHY_UBUS_CONFIGURING);
    if (!guard() || rpi5_pcie_ubus_init(&ubus, &serdes) ||
        rpi5_pcie_ubus_configure(&ubus, &result.ubus) || !guard()) {
        fail();
        return false;
    }
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
