/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_FIRMWARE_FDT_HANDOFF
#error "Firmware FDT copy requires the separate BCM2712 DEVELOPMENT build"
#endif
#include "BCM2712FirmwareFDT.h"
#include <machine/machine_routines.h>
#include "../../osfmk/arm64/rpi5_firmware_fdt_api.h"
extern "C" {
#include "../../loader/rpi5/fdt_sanitize.h"
#include "../../loader/rpi5/firmware_fdt_record.h"
}

OSData *rpi5_copy_boot_firmware_fdt()
{
    const void *source = nullptr;
    size_t bytes = 0;
    if (ml_at_interrupt_context() || !rpi5_firmware_fdt_view(&source, &bytes) ||
        !source || bytes < 40 || bytes > RPI5_FIRMWARE_FDT_MAX_BYTES) return nullptr;
    OSData *copy = OSData::withBytes(source, (unsigned)bytes);
    if (!copy) return nullptr;
    void *buffer = const_cast<void *>(copy->getBytesNoCopy());
    if (copy->getLength() != bytes || !buffer || rpi5_fdt_sanitize_boot_seeds(buffer, bytes)) {
        /* No raw seed-bearing copy is retained on parse failure. */
        if (buffer) for (unsigned i = 0; i < copy->getLength(); i++)
            ((volatile uint8_t *)buffer)[i] = 0;
        copy->release();
        return nullptr;
    }
    return copy;
}
