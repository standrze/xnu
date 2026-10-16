/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_PCIE_CONTROLLER_DIAGNOSTIC
#error "PCIe controller composition requires its separate diagnostic build"
#endif
bool BCM2712PCIePHYTransport::runController(const struct bcm2712_controller_admission *admission,
    struct bcm2712_controller_observation *out)
{
    if (!out || !admission || !admission->check || !onOwnerThread() || !ownerProvider ||
        !ownerProvider->isOpen(this) ||
        getPhase() != BCM2712_PHY_PREPARED || controllerMode) return false;
    /* Retained provider is the callback's only context. Its implementation
     * must supply independent hardware/lifecycle checks, not return a cached
     * registry flag or delegate back to guard. No concrete implementation or
     * hardware boot caller is supplied by this composition. */
    controllerAdmission = *admission;
    lifecyclePhase = BCM2712_CONTROLLER_PRECLAIM;
    controllerMode = true;
    checkingLifecycle = true;
    int admitted = controllerAdmission.check(ownerProvider, lifecyclePhase);
    checkingLifecycle = false;
    if (admitted || getPhase() != BCM2712_PHY_PREPARED || !ownerProvider->isOpen(this)) {
        fail(); return false;
    }
    lifecyclePhase = BCM2712_CONTROLLER_INITIALIZING;
    struct bcm2712_controller_observation result = {};
    if (!runPHYUBUSQoSAndClock(&result.prior)) { fail(); return false; }
    lifecyclePhase = BCM2712_CONTROLLER_HELD_RESET;
    setPhase(BCM2712_PHY_RC_CONFIGURING);
    struct rpi5_pcie_windows_io windowIO = {this, binding.bridge_regs.start,
        binding.bridge_regs.end - binding.bridge_regs.start, controllerQuiescent, bridgeRead, bridgeWrite, order};
    struct rpi5_pcie_rc_io halfIO = {controllerRead16, controllerWrite16};
    if (!guard() || rpi5_pcie_windows_init(&windows, &binding, &windowIO, RPI5_PCIE_WINDOW_ACK_FOUR_BYTES) ||
        rpi5_pcie_rc_init(&rc, &windows, &reset, &calibration, &halfIO) ||
        rpi5_pcie_rc_configure(&rc, &result.rc) || !guard()) { fail(); return false; }
    setPhase(BCM2712_PHY_LINK_TRAINING);
    struct rpi5_pcie_link_io linkIO = {controllerLifecycle, controllerRead16, controllerWrite16, &rc};
    if (!guard() || rpi5_pcie_link_init(&link, &ubus, &windows, &linkIO) ||
        rpi5_pcie_link_train(&link, &result.link) || !guard()) { fail(); return false; }
    setPhase(BCM2712_PHY_CLOCK_FINISHING);
    if (!guard() || rpi5_pcie_clock_finish(&clockPolicy, &link, &result.clock) || !guard()) {
        fail(); return false;
    }
    result.fresh_unused_checks = freshUnusedChecks;
    setPhase(BCM2712_PHY_COMPLETE);
    *out = result;
    return true;
}
