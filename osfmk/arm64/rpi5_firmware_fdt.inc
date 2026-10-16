/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_FIRMWARE_FDT_HANDOFF
#error "Firmware FDT view requires the separate BCM2712 DEVELOPMENT build"
#endif
#include "loader/rpi5/firmware_fdt_record.h"
#include "arm64/rpi5_firmware_fdt_api.h"
static SECURITY_READ_ONLY_LATE(struct rpi5_firmware_fdt_span) rpi5_fdt_source_span;
static SECURITY_READ_ONLY_LATE(vm_offset_t) rpi5_fdt_source_kva;

bool rpi5_firmware_fdt_view(const void **data, size_t *bytes)
{
    if (!data || !bytes || !rpi5_fdt_source_kva || !rpi5_fdt_source_span.bytes) return false;
    *data = (const void *)rpi5_fdt_source_kva;
    *bytes = (size_t)rpi5_fdt_source_span.bytes;
    return true;
}
