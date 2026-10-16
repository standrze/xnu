/* SPDX-License-Identifier: BSD-2-Clause */
#if !RPI5_FIRMWARE_FDT_HANDOFF
#error "Boot-FDT transport preparation requires its separate diagnostic build"
#endif
#include "BCM2712FirmwareFDT.h"
bool BCM2712PCIePHYTransport::prepareBoot(IOService *provider)
{
    if (ml_at_interrupt_context() || getPhase() != BCM2712_PHY_EMPTY) return false;
    OSData *copy = rpi5_copy_boot_firmware_fdt();
    if (!copy) return false;
    /* prepare's actual strict decoder copies the binding into this instance;
     * retain the sanitized full tree too for subsequent original-option checks.
     * prepare's atomic phase claim rejects simultaneous competing preparers. */
    if (!prepare(provider, copy->getBytesNoCopy(), copy->getLength())) {
        copy->release();
        return false;
    }
    firmwareFDT = copy;
    return true;
}
