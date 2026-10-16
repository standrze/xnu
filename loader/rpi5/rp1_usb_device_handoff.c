/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_device_handoff.h"

#include "pcie_fdt.h"
#include "rp1_device_handoff.h"

#define RPI5_RP1_BAR1_CPU_BASE UINT64_C(0x1f00000000)
#define RPI5_RP1_USB0_OFFSET UINT64_C(0x200000)
#define RPI5_RP1_USB0_BYTES UINT64_C(0x100000)

int
rpi5_rp1_usb_device_handoff(const void *fdt, size_t bytes,
    const struct rpi5_memory_types *input, struct rpi5_memory_types *out)
{
    if (!input || !out || input == out || rpi5_memory_types_validate(input)) {
        return -1;
    }

    struct rpi5_memory_types result;
    if (rpi5_rp1_device_handoff(fdt, bytes, input, &result) ||
        result.device.count > 31) {
        return -1;
    }

    struct rpi5_pcie_fdt decoded;
    if (rpi5_fdt_pcie_rp1(fdt, bytes, &decoded) ||
        decoded.outbound_count != 2 ||
        decoded.outbound[0].space != UINT32_C(0x02000000) ||
        decoded.outbound[0].pci_base != 0 ||
        decoded.outbound[0].cpu_base != RPI5_RP1_BAR1_CPU_BASE ||
        decoded.outbound[0].size != UINT64_C(0xfffffffc) ||
        decoded.rp1_pci_base != 0 ||
        decoded.rp1_aperture_size != UINT64_C(0x410000) ||
        RPI5_RP1_USB0_OFFSET > decoded.rp1_aperture_size ||
        RPI5_RP1_USB0_BYTES > decoded.rp1_aperture_size - RPI5_RP1_USB0_OFFSET ||
        RPI5_RP1_USB0_OFFSET > decoded.outbound[0].size ||
        RPI5_RP1_USB0_BYTES > decoded.outbound[0].size - RPI5_RP1_USB0_OFFSET) {
        return -1;
    }

    const struct rpi5_range added = {
        RPI5_RP1_BAR1_CPU_BASE + RPI5_RP1_USB0_OFFSET,
        RPI5_RP1_BAR1_CPU_BASE + RPI5_RP1_USB0_OFFSET + RPI5_RP1_USB0_BYTES,
    };
    size_t position = 0;
    for (size_t i = 0; i < result.device.count; i++) {
        const struct rpi5_range old = result.device.extent[i];
        if (old.start < added.end && added.start < old.end) {
            return -1;
        }
        if (old.start < added.start) {
            position++;
        }
    }
    for (size_t i = result.device.count; i > position; i--) {
        result.device.extent[i] = result.device.extent[i - 1];
    }
    result.device.extent[position] = added;
    result.device.count++;
    if (rpi5_memory_types_validate(&result)) {
        return -1;
    }
    *out = result;
    return 0;
}
