/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_CLOCK_DIAGNOSTIC
#error "PCIe clock advertisement requires its separate diagnostic build"
#endif
bool BCM2712PCIePHYTransport::runPHYUBUSQoSAndClock(struct bcm2712_clock_observation *out)
{
    if (!out || !onOwnerThread() || getPhase() != BCM2712_PHY_PREPARED) return false;
    struct bcm2712_clock_observation result = {};
    /* Actual prior operations with their real sessions, not synthetic
     * COMPLETE flags or a second watchdog claim. No PERST release here. */
    if (!runPHYUBUSWindowAndQoS(&result.prior)) return false;
    setPhase(BCM2712_PHY_CLOCK_PREPARING);
    if (!guard() || rpi5_pcie_clock_init(&clockPolicy, &qos) ||
        rpi5_pcie_clock_prepare(&clockPolicy, &result.clock) || !guard()) {
        fail(); return false;
    }
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
/* Post-link clock_finish is compiled into this complete kernel, but not
 * called here: genuine RC/windows/link and lifecycle admission are still
 * required. Do not fabricate a COMPLETE link or reuse unusedOwner as the
 * missing power/clock/IRQ/endpoint/DMA-quiescence check_lifecycle provider. */
