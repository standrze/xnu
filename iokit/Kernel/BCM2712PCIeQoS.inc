/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_PROFILE_QOS_DIAGNOSTIC
#error "Firmware profile/QoS requires its separate diagnostic build"
#endif
bool BCM2712PCIePHYTransport::runPHYUBUSWindowAndQoS(struct bcm2712_qos_observation *out)
{
    if (!out || !onOwnerThread() || getPhase() != BCM2712_PHY_PREPARED) return false;
    struct bcm2712_qos_observation result = {};
    /* Calls all real previous stages, never fabricates completed dependencies
     * or claims another watchdog lease. Profile was decoded before mapping. */
    if (!runPHYUBUSAndWindowCheck(&result.prior)) return false;
    setPhase(BCM2712_PHY_QOS_CONFIGURING);
    if (!guard() || rpi5_pcie_qos_init(&qos, &ubus, &profile, unusedOwner) ||
        rpi5_pcie_qos_configure(&qos, &result.qos) || !guard()) {
        fail(); return false;
    }
    result.profile = profile;
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
